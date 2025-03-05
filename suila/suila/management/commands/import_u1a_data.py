# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
from collections import defaultdict
from dataclasses import fields
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, ConfigDict
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from suila.integrations.akap.u1a import (
    AKAPU1AItem,
    get_akap_u1a_items,
    get_akap_u1a_items_unique_cprs,
)
from suila.management.commands.common import SuilaBaseCommand
from suila.models import (
    DataLoad,
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)

logger = logging.getLogger(__name__)


class ImportResult(BaseModel):
    import_year: int
    cprs_handled: int = 0
    assessments_created: int = 0
    assessments_updated: int = 0
    monthly_income_reports_created: int = 0
    monthly_income_reports_updated: int = 0


class PersonMonthReport(BaseModel):
    person_month: PersonMonth
    employer: Employer

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
        self.verbose = kwargs.get("verbose", None)

        # Configure years
        if year is None:
            years = Year.objects.all().order_by("year")
        else:
            fetched_year, _ = Year.objects.get_or_create(year=year)
            years = [fetched_year]

        # Output of the process about to
        self._write_verbose("Running AKAP U1A data import:")
        self._write_verbose(f"- Host: {settings.AKAP_HOST}")
        self._write_verbose(f"- year(s): {[y.year for y in years]}")
        self._write_verbose(f"- CPR: {cpr}\n")

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
                results.append(self._import_data(data_load, year, cpr))
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
                f"MonthlyIncomeReports created: {result.monthly_income_reports_created}"
            )
            logger.info(
                f"MonthlyIncomeReports updated: {result.monthly_income_reports_updated}"
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
    ) -> ImportResult:
        result = ImportResult(import_year=year.year)

        u1a_cprs: List[str] = [cpr] if cpr else []
        if len(u1a_cprs) == 0:
            # Get all unique CPRs in that year (from AKAP api)
            self._write_verbose(f"- No CPR specified, fetching all for year: {year}")
            u1a_cprs = get_akap_u1a_items_unique_cprs(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year.year,
                fetch_all=True,
            )

            self._write_verbose(f"- Fetched CPRs: {u1a_cprs}")

        if len(u1a_cprs) < 1:
            return result

        # Get Person objects for the CPR
        self._write_verbose(f"- Fetching persons from CPRs: {u1a_cprs}")

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

        objs_to_create = {}
        objs_to_update = {}

        for person in persons:
            self._write_verbose(
                f"- Fetching U1A items for person: {person} ({person.cpr})"
            )

            # Fetch items and group them by u1a.id
            person_akap_u1a_items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year=year.year,
                cpr=person.cpr,
                fetch_all=True,
            )

            u1a_items_dict: Dict[int, List[AKAPU1AItem]] = defaultdict(list)
            for item in person_akap_u1a_items:
                u1a_items_dict[item.u1a.id].append(item)

            # Get, or create, PersonYear
            person_year, _ = PersonYear.objects.get_or_create(person=person, year=year)

            # Update, or create, MonthlyIncomeReports for each U1A
            for _, u1a_items in u1a_items_dict.items():
                u1a = u1a_items[0].u1a
                u1a_month = u1a.dato_udbetaling.month

                # Get U1A Employer & PersonMonth (or create them)
                u1a_employer, created = Employer.objects.get_or_create(
                    cvr=u1a.cvr, defaults={"load": data_load}
                )
                if created:
                    self._write_verbose("\t- Created 1 Employer object")

                u1a_person_month, created = PersonMonth.objects.get_or_create(
                    person_year=person_year,
                    month=u1a_month,
                    defaults={"load": data_load},
                )
                if created:
                    self._write_verbose("\t- Created 1 PersonMonth object(s)")

                # Reset existing MonthlyIncomeReport, with U-income,
                # and update related PersonMonth.amount_sum
                existing_u1a_reports = MonthlyIncomeReport.objects.filter(
                    employer=u1a_employer,
                    person_month=u1a_person_month,
                    u_income__gt=Decimal(0),
                )

                if len(existing_u1a_reports) > 0:
                    for existing_report in existing_u1a_reports:
                        existing_report.person_month.amount_sum -= (
                            existing_report.u_income
                        )
                        existing_report.person_month.save()

                        existing_report.u_income = Decimal("0.00")
                        existing_report.save()

                    logger.info(
                        (
                            f"\t- Removed U-income from {len(existing_u1a_reports)} "
                            "existing MonthlyIncomeReport(s)"
                        )
                    )

                # Add U-income to MonthlyIncomeReport (or create it)
                field_values: Dict[str, Any] = {"u_income": u1a.udbytte}
                key = (
                    person.cpr,
                    person_year.year.year,
                    u1a_person_month.month,
                    u1a.cvr,
                )

                try:
                    report = MonthlyIncomeReport.objects.get(
                        employer=u1a_employer,
                        person_month=u1a_person_month,
                    )
                except MonthlyIncomeReport.DoesNotExist:
                    report = MonthlyIncomeReport(
                        employer=u1a_employer,
                        person_month=u1a_person_month,
                        load=data_load,
                        **field_values,
                    )
                    report.update_amount()
                    objs_to_create[key] = report
                else:
                    # An existing monthly income report exists
                    # for this person month and employer - update it.
                    changed = False
                    for field_name, field_value in field_values.items():
                        if getattr(report, field_name) != field_value:
                            setattr(report, field_name, field_value)
                            changed = True

                    if changed:
                        report.update_amount()
                        objs_to_update[key] = report

            result.cprs_handled += 1

        # Create & update in bulk
        objs_to_create_list = list(objs_to_create.values())
        objs_to_update_list = list(objs_to_update.values())

        bulk_create_with_history(
            objs_to_create_list,
            MonthlyIncomeReport,
        )
        result.monthly_income_reports_created = len(objs_to_create_list)

        bulk_update_with_history(
            objs_to_update_list,
            MonthlyIncomeReport,
            [f.name for f in MonthlyIncomeReport._meta.fields if not f.primary_key],
        )
        result.monthly_income_reports_updated = len(objs_to_update_list)

        return result

    def _parse_value(self, name: str, value: Any) -> Any:
        if name == "valid_from":
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.get_current_timezone()
            )
        return Decimal(value)

    def _get_field_values(
        self,
        item: Any,
        default: int = 0,
        exclude: set[str] | None = None,
    ) -> dict[str, Any]:
        if exclude is None:
            exclude = set()
        return {
            f.name: self._parse_value(f.name, getattr(item, f.name) or default)
            for f in fields(item)
            if f.name not in exclude
        }

    def _write_verbose(self, message: str):
        if self.verbose:
            logger.info(message)
