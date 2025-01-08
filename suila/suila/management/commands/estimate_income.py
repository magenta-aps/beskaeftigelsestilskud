# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import time
from typing import List

from django.db import transaction

from suila.estimation import EstimationEngine
from suila.management.commands.common import SuilaBaseCommand
from suila.models import Person, Year


class Command(SuilaBaseCommand):
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

        for year in years:
            EstimationEngine.estimate_all(year, person, count, dry, output_stream)

        if verbose:
            duration = datetime.datetime.utcfromtimestamp(time.time() - start)
            self.stdout.write(f"Done (took {duration.strftime('%H:%M:%S')})")
