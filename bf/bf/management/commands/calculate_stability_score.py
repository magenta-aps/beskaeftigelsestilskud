# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from cProfile import Profile

from django.core.management.base import BaseCommand

from bf.models import IncomeType, PersonYear


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--cpr", type=int)
        parser.add_argument("--profile", action="store_true", default=False)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose(f"Calculating stability score for {kwargs['year']}")

        if kwargs["cpr"]:
            years = PersonYear.objects.filter(
                year__year=kwargs["year"],
                person__cpr=kwargs["cpr"],
            )
        else:
            years = PersonYear.objects.filter(
                year__year=kwargs["year"],
            )
        for person_year in years:
            for income_type in IncomeType:
                person_year.calculate_stability_score(income_type)
            person_year.save()

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
