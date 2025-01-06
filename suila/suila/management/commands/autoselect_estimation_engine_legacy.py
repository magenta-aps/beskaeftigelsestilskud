# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from django.core.management.base import BaseCommand

from suila.models import IncomeType, Person, PersonYear, PersonYearEstimateSummary


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        for person in Person.objects.all():
            for income_type in IncomeType:
                preferred_estimation_engine_field = (
                    f"preferred_estimation_engine_{income_type.value.lower()}"
                )

                summaries = PersonYearEstimateSummary.objects.filter(
                    person_year__person=person,
                    income_type=income_type,
                ).order_by("person_year__year")
                years = set([summary.person_year.year.year for summary in summaries])

                for year in [y for y in years if y != min(years)]:
                    # Look for LAST year's results to find the best estimation
                    # engine for THIS year
                    relevant_summaries = [
                        summary
                        for summary in summaries
                        if summary.person_year.year.year == year - 1
                        and summary.rmse_percent is not None
                    ]
                    rmses = {
                        summary.estimation_engine: summary.rmse_percent
                        for summary in relevant_summaries
                    }

                    if rmses:
                        best_engine = min(rmses, key=rmses.get)
                        person_year = PersonYear.objects.get(person=person, year=year)
                        setattr(
                            person_year,
                            preferred_estimation_engine_field,
                            best_engine,
                        )
                        person_year.save(
                            update_fields=(preferred_estimation_engine_field,)
                        )

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
