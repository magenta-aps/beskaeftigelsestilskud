# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import logging
import time
from typing import List

from django.db import transaction

from bf.estimation import EstimationEngine
from bf.management.commands.common import BfBaseCommand
from bf.models import Person, Year

logger = logging.getLogger(__name__)


class Command(BfBaseCommand):
    filename = __file__

    engines: List[EstimationEngine] = EstimationEngine.instances()

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--count", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        start = time.time()

        verbose = kwargs["verbosity"] > 1
        dry = kwargs["dry"]
        year = kwargs["year"]
        cpr = kwargs["cpr"]
        count = kwargs["count"]

        person = Person.objects.get(cpr=cpr).pk if cpr else None
        output_stream = self.stdout if verbose else None

        if year is None:
            years = Year.objects.all().order_by("year").values_list("year", flat=True)
        else:
            years = [year]

        try:
            for year in years:
                EstimationEngine.estimate_all(year, person, count, dry, output_stream)
        except Exception:
            logger.exception(
                f"ERROR running EstimationEngine.estimate_all() for years: {years}"
            )
            transaction.set_rollback(True)

        if verbose:
            duration = datetime.datetime.utcfromtimestamp(time.time() - start)
            self.stdout.write(f"Done (took {duration.strftime('%H:%M:%S')})")
