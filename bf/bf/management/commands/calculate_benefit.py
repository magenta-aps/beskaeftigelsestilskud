# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from cProfile import Profile

from django.core.management.base import BaseCommand

from bf.exceptions import EstimationEngineUnset
from bf.models import PersonMonth


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--cpr", type=int)
        parser.add_argument("--profile", action="store_true", default=False)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1

        self._write_verbose(f"Calculating benefit for {kwargs['year']}")

        months = PersonMonth.objects.filter(
            person_year__year__year=kwargs["year"],
        )
        if kwargs["cpr"]:
            months = months.filter(
                person_year__person__cpr=kwargs["cpr"],
            )
        months = months.filter(incomeestimate__isnull=False)

        month = kwargs["month"]
        if month and month >= 1 and month <= 12:
            months = months.filter(month=month)
            month_range = [month]
        else:
            month_range = range(1, 13)

        for month_number in month_range:
            month_qs = (
                months.filter(month=month_number)
                .select_related("person_year")
                .prefetch_related("incomeestimate_set")
                .distinct()
            )
            for person_month in month_qs:
                try:
                    person_month.calculate_benefit()
                except EstimationEngineUnset as e:
                    self._write_verbose(str(e))
            PersonMonth.objects.bulk_update(
                month_qs,
                fields=[
                    "benefit_paid",
                    "prior_benefit_paid",
                    "actual_year_benefit",
                    "estimated_year_benefit",
                ],
                batch_size=1000,
            )
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
