# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from common.utils import get_best_engine
from django.core.management.base import BaseCommand

from bf.models import PersonYear


class Command(BaseCommand):

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("year", type=int)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year = kwargs["year"]
        self._write_verbose(f"Running autoselect algorithm for {year}")
        best_engine = get_best_engine(year)

        # Bulk update
        person_years_to_update = []
        person_years = PersonYear.objects.filter(year=year).select_related("person")
        for person_year in person_years:
            cpr = person_year.person.cpr
            if cpr in best_engine.index:
                person_year.preferred_estimation_engine_a = best_engine.loc[cpr, "A"]
                person_year.preferred_estimation_engine_b = best_engine.loc[cpr, "B"]
                person_years_to_update.append(person_year)

        PersonYear.objects.bulk_update(
            person_years_to_update,
            ["preferred_estimation_engine_a", "preferred_estimation_engine_b"],
            batch_size=1000,
        )
        self._write_verbose("Done")

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
