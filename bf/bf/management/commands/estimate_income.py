# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import math
import time
from cProfile import Profile
from decimal import Decimal
from itertools import groupby
from operator import attrgetter
from typing import Iterable, List

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Func, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from tabulate import tabulate

from bf.data import MonthlyIncomeData
from bf.estimation import EstimationEngine
from bf.models import (
    IncomeEstimate,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
)


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

        self._year = kwargs["year"]
        self._verbose = kwargs["verbosity"] > 1
        self._dry = kwargs["dry"]

        person_year_qs = PersonYear.objects.filter(
            year__year=self._year
        ).select_related("person")
        if kwargs["count"]:
            person_year_qs = person_year_qs[: kwargs["count"]]
        if kwargs["person"]:
            person_year_qs = person_year_qs.filter(person=kwargs["person"])

        if not self._dry:
            self._write_verbose("Removing current `IncomeEstimate` objects ...")
            IncomeEstimate.objects.filter(
                person_month__person_year__in=person_year_qs
            ).delete()

            self._write_verbose(
                "Removing current `PersonYearEstimateSummary` objects ..."
            )
            PersonYearEstimateSummary.objects.filter(
                person_year__in=person_year_qs
            ).delete()

        self._write_verbose("Fetching income data ...")
        data_qs = self._get_data_qs(person_year_qs)
        self._person_month_map = {pm.pk: pm for pm in PersonMonth.objects.all()}

        self._write_verbose("Computing estimates ...")
        results = []
        summaries = []
        for idx, subset in enumerate(self._iterate_by_person(data_qs)):
            self._write_verbose(f"{idx}", ending="\r")
            person_pk = subset[0].person_pk
            first_income_month = 1
            for month_data in subset:
                if not month_data.amount.is_zero():
                    first_income_month = month_data.month
                    break

            person_year = person_year_qs.get(person_id=person_pk)
            for engine in self.engines:
                for income_type in engine.valid_income_types:
                    engine_results = []
                    for month in range(first_income_month, 13):
                        person_month = self._get_person_month_for_row(
                            subset, self._year, month
                        )

                        actual_year_sum = sum(
                            row.a_amount if income_type == "A" else row.b_amount
                            for row in subset
                            if row.year == self._year and row.month <= month
                        )
                        if person_month is not None:
                            result: IncomeEstimate = engine.estimate(
                                person_month, subset, income_type
                            )
                            if result is not None:
                                result.person_month = person_month
                                result.actual_year_result = actual_year_sum
                                engine_results.append(result)
                                results.append(result)

                    # If we do not have month 12 in the dataset we do not know
                    # what the real income is and can therefore
                    # not evaluate our estimations
                    if (
                        engine_results
                        and actual_year_sum
                        and engine_results[-1].person_month.month == 12
                    ):
                        actual_year_result = engine_results[-1].actual_year_result
                        months_without_income = 12 - len(engine_results)

                        monthly_estimates = [Decimal(0)] * months_without_income + [
                            resultat.estimated_year_result
                            for resultat in engine_results
                        ]

                        # Mean error
                        mean_error = Decimal(
                            sum(
                                [
                                    estimate - actual_year_result
                                    for estimate in monthly_estimates
                                ]
                            )
                            / 12
                        )

                        # Root-mean-squared-error
                        rmse = Decimal(
                            math.sqrt(
                                sum(
                                    [
                                        (estimate - actual_year_result) ** 2
                                        for estimate in monthly_estimates
                                    ]
                                )
                                / 12
                            )
                        )

                        mean_error_percent = 100 * mean_error / actual_year_sum
                        rmse_percent = 100 * rmse / actual_year_sum
                    else:
                        mean_error_percent = None
                        rmse_percent = None

                    summary = PersonYearEstimateSummary(
                        person_year=person_year,
                        estimation_engine=engine.__class__.__name__,
                        income_type=income_type,
                        mean_error_percent=mean_error_percent,
                        rmse_percent=rmse_percent,
                    )
                    summaries.append(summary)

        if not self._dry:
            self._write_verbose(f"Writing {len(results)} `IncomeEstimate` objects ...")
            IncomeEstimate.objects.bulk_create(results, batch_size=1000)
            PersonYearEstimateSummary.objects.bulk_create(summaries, batch_size=1000)
        elif self._dry and kwargs["person"]:
            self._write_verbose(
                tabulate(
                    [
                        {
                            "engine": r.engine,
                            "year": r.person_month.year,
                            "month": r.person_month.month,
                            "actual": r.actual_year_result,
                            "estimate": r.estimated_year_result,
                        }
                        for r in results
                    ],
                    headers="keys",
                )
            )

        duration = datetime.datetime.utcfromtimestamp(time.time() - start)
        self._write_verbose(f"Done (took {duration.strftime('%H:%M:%S')})")

    def _get_data_qs(
        self, person_year_qs: QuerySet[PersonYear]
    ) -> List[MonthlyIncomeData]:
        # Return queryset with one row for each `PersonMonth`.
        # Each row contains PKs for person, person month, and values for year and month.
        # Each row also contains summed values for monthly reported A and B income, as
        # each person month can have one or more A or B incomes reported.

        def sum_amount(incomereport_class):
            return Subquery(
                incomereport_class.objects.filter(
                    month=OuterRef("month"),
                    year=OuterRef("year"),
                    person=OuterRef("person_pk"),
                )
                .annotate(
                    sum_amount=Coalesce(Func("amount", function="Sum"), Decimal(0))
                )
                .values("sum_amount")
            )

        qs = (
            PersonMonth.objects.filter(
                person_year__person__in=person_year_qs.values("person")
            )
            .values(
                "month",
                person_pk=F("person_year__person__pk"),
                person_month_pk=F("pk"),
                year=F("person_year__year__year"),
            )
            .annotate(
                a_amount=sum_amount(MonthlyAIncomeReport),
                b_amount=sum_amount(MonthlyBIncomeReport),
            )
            .order_by(
                "person_pk",
                "year",
                "month",
            )
        )
        return [MonthlyIncomeData(**value) for value in qs]

    def _iterate_by_person(
        self, data_qs: List[MonthlyIncomeData]
    ) -> Iterable[List[MonthlyIncomeData]]:
        # Iterate over `data_qs` and yield a subset of rows for each `_person_pk`
        return (
            list(vals) for key, vals in groupby(data_qs, key=attrgetter("person_pk"))
        )

    def _get_person_month_for_row(
        self, subset: List[MonthlyIncomeData], year: int, month: int
    ) -> int | None:
        for item in subset:
            if item.year == year and item.month == month:
                return self._person_month_map[item.person_month_pk]
        return None

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
