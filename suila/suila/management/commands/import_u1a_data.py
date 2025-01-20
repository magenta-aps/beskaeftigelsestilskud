# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from suila.integrations.akap.u1a import (
    AKAPU1AItem,
    get_akap_u1a_items,
    get_akap_u1a_items_unique_cprs,
)
from suila.management.commands.common import SuilaBaseCommand
from suila.models import DataLoad, Person, PersonYear, PersonYearU1AAssessment, Year

logger = logging.getLogger(__name__)


class ImportResult(BaseModel):
    import_year: int
    cprs_handled: int = 0
    assessments_created: int = 0
    assessments_updated: int = 0


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--verbose", action="store_true")
        super().add_arguments(parser)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        dry = kwargs.get("dry", False)
        year = kwargs.get("year", None)
        cpr = kwargs.get("cpr", None)
        verbose = kwargs.get("verbose", None)

        # Configure years
        if year is None:
            years = Year.objects.all().order_by("year")
        else:
            fetched_year, _ = Year.objects.get_or_create(year=year)
            years = [fetched_year]

        # Output of the process about to
        if verbose:
            logger.info("Running AKAP U1A data import:")
            logger.info(f"- Host: {settings.AKAP_HOST}")
            logger.info(f"- year(s): {[y.year for y in years]}")
            logger.info(f"- CPR: {cpr}\n")

        # Create a DataLoad object for this import
        data_load: DataLoad = DataLoad.objects.create(
            source="api",
            parameters={"host": settings.AKAP_HOST, "name": "AKAP udbytte U1A API"},
        )

        # Import data for each year
        results: List[ImportResult] = []
        for year in years:
            logger.info(f"Importing: U1A entries for year {year} (CPR={cpr})")
            try:
                results.append(self._import_data(data_load, year, cpr, verbose))
            except Exception as e:
                logger.exception("IMPORT ERROR!")
                raise e

        # Rollback everything if DRY-run is used
        if dry:
            transaction.set_rollback(True)
            logger.info("Dry run complete. All changes rolled back.")

        # Finish
        logger.info("-------------------- REPORT --------------------")
        for idx, result in enumerate(results):
            logger.info(f"Year: {result.import_year}")
            logger.info(f"CPRs handled: {result.cprs_handled}")
            logger.info(
                f"PersonYear U1A Assessments created: {result.assessments_created}"
            )
            logger.info(
                f"PersonYear U1A Assessments updated: {result.assessments_updated}"
            )

            if idx < len(results) - 1:
                logger.info("")
        logger.info("------------------------------------------------")
        logger.info("DONE!")

    def _import_data(
        self,
        data_load: DataLoad,
        year: Year,
        cpr: Optional[str] = None,
        verbose: Optional[bool] = None,
    ) -> ImportResult:
        result = ImportResult(import_year=year.year)

        u1a_cprs: List[str] = [cpr] if cpr else []
        if len(u1a_cprs) == 0:
            # Get all unique CPRs in that year (from AKAP api)
            if verbose:
                logger.info(f"- No CPR specified, fetching all for year: {year}")

            u1a_cprs = get_akap_u1a_items_unique_cprs(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year.year,
                fetch_all=True,
            )

            if verbose:
                logger.info(f"- Fetched CPRs: {u1a_cprs}")

        if len(u1a_cprs) < 1:
            return result

        # Get Person objects for the CPR
        if verbose:
            logger.info(f"- Fetching persons from CPRs: {u1a_cprs}")

        persons: List[Person] = []
        for u1a_cpr in u1a_cprs:
            try:
                person = Person.objects.get(cpr=u1a_cpr)
                persons.append(person)
            except Person.DoesNotExist:
                logger.warning(f"Could not find Person with CPR: {u1a_cpr}, skipping!")
                continue

        if len(persons) < 1:
            return result

        # Go through each person and create a PersonYearU1AAssessment
        for person in persons:
            if verbose:
                logger.info(f"- Fetching U1A items for person: {person}")

            person_akap_u1a_items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year=year.year,
                cpr=person.cpr,
                fetch_all=True,
            )

            u1a_items_dict: Dict[int, List[AKAPU1AItem]] = {}
            for item in person_akap_u1a_items:
                if item.u1a_id not in u1a_items_dict:
                    u1a_items_dict[item.u1a_id] = []
                u1a_items_dict[item.u1a_id].append(item)

            # Calculate total divident
            dividend_total: Decimal = Decimal(0)
            for _, u1a_items in u1a_items_dict.items():
                for u1a_item in u1a_items:
                    dividend_total += u1a_item.udbytte

            # Get, or create, PersonYear
            person_year, _ = PersonYear.objects.get_or_create(person=person, year=year)

            # Create or update assessemt
            if verbose:
                logger.info(f"- Creating PersonYearU1AAssessment for person: {person}")

            u1a_ids_str = ", ".join(str(u1a_id) for u1a_id in u1a_items_dict.keys())
            _, created = PersonYearU1AAssessment.objects.update_or_create(
                person_year=person_year,
                u1a_ids=u1a_ids_str,
                defaults={"dividend_total": dividend_total, "load": data_load},
            )

            if created:
                result.assessments_created += 1
            else:
                result.assessments_updated += 1

            result.cprs_handled += 1

        return result
