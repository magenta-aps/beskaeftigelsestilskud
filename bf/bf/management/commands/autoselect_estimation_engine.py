# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from django.core.management.base import BaseCommand

from bf.data import engine_keys
from bf.models import PersonMonth, PersonYear


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
        person_years = PersonYear.objects.filter(year=year)
        for person_year in person_years:
            # Only calculate benefit for last year to find the best engine for the
            # upcoming year.
            person_months = PersonMonth.objects.filter(person_year=person_year.prev)

            # Load december because it contains the actual payout that should have been
            # paid over the course of a year.
            try:
                december = person_months.get(month=12)
            except PersonMonth.DoesNotExist:
                # If the person does not have december we cannot auto-select
                continue

            actual_year_benefit = december.actual_year_benefit

            if not actual_year_benefit:
                # If the person does not have benefit in december we cannot auto-select
                continue

            best_engine_dict = {}

            # 62065: SameAsLastMonthEngine tends to miss the end-of-year mark,
            # meaning the estimated and actual sum in december don't match
            engines = [
                engine_name
                for engine_name in engine_keys
                if engine_name != "SameAsLastMonthEngine"
            ]

            # Test all combinations of A and B engines
            for engine_a in engines:
                for engine_b in engines:
                    benefit = sum(
                        [
                            m.calculate_benefit(engine_a=engine_a, engine_b=engine_b)
                            for m in person_months
                        ]
                    )

                    # Store the difference between the amount that was paid out
                    # and the amount that should have been paid out for each engine
                    # combination
                    best_engine_dict[(engine_a, engine_b)] = abs(
                        benefit - actual_year_benefit
                    )

            # Get the best engine for each income type
            best_engines = min(best_engine_dict, key=best_engine_dict.get)

            # Save them onto the person_year model
            for income_type, best_engine in zip(["a", "b"], best_engines):
                preferred_estimation_engine_field = (
                    f"preferred_estimation_engine_{income_type}"
                )
                setattr(
                    person_year,
                    preferred_estimation_engine_field,
                    best_engine,
                )
                person_year.save(update_fields=(preferred_estimation_engine_field,))

        self._write_verbose("Done")

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
