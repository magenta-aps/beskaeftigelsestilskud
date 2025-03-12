# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from django.core.management.base import BaseCommand

from suila.models import IncomeType, Person, PersonYear, PersonYearEstimateSummary


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("year", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        parameter = "mean_error_percent"  # eller "rmse_percent"
        person_qs = Person.objects.all()
        first_year = PersonYear.objects.order_by("year").values_list("year_id").first()
        if kwargs["cpr"]:
            person_qs = person_qs.filter(cpr=kwargs["cpr"])
        for person in person_qs:
            for income_type in (IncomeType.A, IncomeType.U):
                preferred_estimation_engine_field = (
                    f"preferred_estimation_engine_{income_type.value.lower()}"
                )
                summaries = PersonYearEstimateSummary.objects.filter(
                    person_year__person=person,
                    income_type=income_type,
                )
                if kwargs["year"]:
                    years = [kwargs["year"]]
                else:
                    years = set(
                        [summary.person_year.year.year for summary in summaries]
                    )

                for year in [y for y in years if y != first_year]:
                    # Look for LAST year's results to find the best estimation
                    # engine for THIS year
                    relevant_summaries = summaries.filter(
                        person_year__year_id=year - 1
                    ).filter(**{f"{parameter}__isnull": False})
                    offsets = {
                        summary.estimation_engine: abs(getattr(summary, parameter))
                        for summary in relevant_summaries
                    }

                    if offsets:
                        best_engine = min(offsets, key=offsets.get)
                        try:
                            person_year = PersonYear.objects.get(
                                person=person, year=year
                            )
                        except PersonYear.DoesNotExist:
                            print(f"No PersonYear found for {person}")
                            continue
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
