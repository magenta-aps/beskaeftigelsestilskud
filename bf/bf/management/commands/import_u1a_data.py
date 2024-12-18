# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
import time
from typing import List, Optional

from django.db import transaction
from pydantic import BaseModel

from bf.management.commands.common import BfBaseCommand
from bf.models import Year

logger = logging.getLogger(__name__)


class ImportResult(BaseModel):
    cprs_handled: int = 0
    assessments_created: int = 0
    assessments_updated: int = 0


class Command(BfBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--verbose", action="store_true")
        super().add_arguments(parser)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        start = time.time()
        dry = kwargs.get("dry", False)
        year = kwargs.get("year", None)
        cpr = kwargs.get("cpr", None)
        verbose = kwargs.get("verbose", None)

        # Configure years
        if year is None:
            years = Year.objects.all().order_by("year").values_list("year", flat=True)
        else:
            years = [year]

        for year in years:
            logger.info(f"Importing: U1A entries for year {year} (CPR={cpr})")
            result = self._import_data(year, cpr, verbose)

        # Rollback everything if DRY-run is used
        if dry:
            transaction.set_rollback(True)
            logger.info("Dry run complete. All changes rolled back.")

        # Finish
        duration = time.time() - start
        logger.info(f"Report: Years convered: {", ".join([str(y) for y in years])}")
        logger.info(f"Report: CPRs handled: {result.cprs_handled}")
        logger.info(
            f"Report: PersonYear U1A Assessments created: {result.assessments_created}"
        )
        logger.info(
            f"Report: PersonYear U1A Assessments updated: {result.assessments_updated}"
        )
        logger.info(f"Report: Exec time: {duration:.3f}s")
        logger.info("DONE!")

    def _import_data(
        self,
        year: int,
        cpr: Optional[str] = None,
        verbose: Optional[bool] = None,
    ):
        result = ImportResult()

        u1a_cprs: List[str] = [cpr] if cpr else []
        if len(u1a_cprs) == 0:
            # TODO: Get all CPRs from the AKAP API (in that year!)
            pass

        # TODO: Get all U1AItem's for the CPR in the given year.
        # cpr_u1a_items: Dict[str, List[int]] = {}

        return result
