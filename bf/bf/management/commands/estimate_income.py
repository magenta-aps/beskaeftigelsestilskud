# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import time
from cProfile import Profile
from typing import List

from django.core.management.base import BaseCommand
from django.db import transaction

from bf.estimation import EstimationEngine


class Command(BaseCommand):
    engines: List[EstimationEngine] = EstimationEngine.instances()

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--count", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--person", type=int)
        parser.add_argument("--profile", action="store_true", default=False)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        start = time.time()

        verbose = kwargs["verbosity"] > 1
        dry = kwargs["dry"]
        year = kwargs["year"]
        person = kwargs["person"]
        count = kwargs["count"]

        output_stream = self.stdout if verbose else None

        EstimationEngine.estimate_all(year, person, count, dry, output_stream)

        if verbose:
            duration = datetime.datetime.utcfromtimestamp(time.time() - start)
            self.stdout.write(f"Done (took {duration.strftime('%H:%M:%S')})")

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
