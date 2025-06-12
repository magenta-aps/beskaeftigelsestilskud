# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from django.core.management.base import BaseCommand

from suila.models import IncomeType, Person, PersonYear, PersonYearEstimateSummary, Year


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("--year", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1

        person_qs = Person.objects.all()
        first_year = (
            PersonYear.objects.order_by("year").values_list("year_id").first()[0]
        )
        if kwargs["cpr"]:
            person_qs = person_qs.filter(cpr=kwargs["cpr"])

        total_count = len(person_qs)
        for counter, person in enumerate(person_qs, start=1):
            self._write_verbose("-" * 100)
            self._write_verbose(
                f"Processing person {counter}/{total_count}: {person.name}"
            )

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
                        [summary.person_year.year.year + 1 for summary in summaries]
                    )

                years_to_process = [y for y in years if y != first_year]

                if not years_to_process:
                    self._write_verbose(
                        (
                            f"No relevant years found for {person.name} "
                            f"(income type = {income_type})"
                        )
                    )

                for year in years_to_process:
                    # Look for LAST year's results to find the best estimation
                    # engine for THIS year

                    year_obj, _ = Year.objects.get_or_create(year=year)

                    relevant_summaries = summaries.filter(
                        person_year__year_id=year - 1, rmse_percent__isnull=False
                    )
                    rmses = {
                        summary.estimation_engine: summary.rmse_percent
                        for summary in relevant_summaries
                    }

                    if not relevant_summaries:
                        self._write_verbose(
                            (
                                f"No relevant PersonYearEstimateSummaries for "
                                f"'{person.name}' - {year-1} "
                                f"(income type = {income_type})"
                            )
                        )

                    if rmses:
                        best_engine = min(rmses, key=rmses.get)
                        person_year, _ = PersonYear.objects.get_or_create(
                            person=person, year=year_obj
                        )

                        self._write_verbose(
                            (
                                f"Obtained engine for "
                                f"{person_year.person.name}: {best_engine} "
                                f"(income type = {income_type})"
                            )
                        )
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
