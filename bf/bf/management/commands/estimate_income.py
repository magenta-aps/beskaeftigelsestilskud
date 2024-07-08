# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import time
from decimal import Decimal
from itertools import groupby
from operator import itemgetter
from typing import Dict, Iterable, List

from data_analysis.models import IncomeEstimate, PersonYearEstimateSummary
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import DecimalField, F, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from tabulate import tabulate

from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import PersonMonth, PersonYear


class Command(BaseCommand):
    engines: List[EstimationEngine] = [
        InYearExtrapolationEngine(),
        TwelveMonthsSummationEngine(),
    ]

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--count", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--person", type=int)

    @transaction.atomic
    def handle(self, *args, **kwargs):
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

        self._write_verbose("Fetching income data ...")
        data_qs = self._get_data_qs(person_year_qs)
        self._person_month_map = {pm.pk: pm for pm in PersonMonth.objects.all()}

        self._write_verbose("Computing estimates ...")
        results = []
        summaries = []
        for idx, subset in enumerate(self._iterate_by_person(data_qs)):
            self._write_verbose(f"{idx}", ending="\r")
            actual_year_sum = sum(
                row["_a_amount"] + row["_b_amount"]
                for row in subset
                if row["_year"] == self._year
            )
            person_pk = subset[0]["_person_pk"]
            person_year = person_year_qs.get(person_id=person_pk)
            for engine in self.engines:
                engine_results = []
                for month in range(1, 13):
                    person_month = self._get_person_month_for_row(
                        subset, self._year, month
                    )
                    if person_month is not None:
                        result: IncomeEstimate = engine.estimate(
                            subset, self._year, month
                        )
                        if result is not None:
                            result.person_month = person_month
                            result.actual_year_result = actual_year_sum
                            engine_results.append(result)
                            results.append(result)
                if engine_results and actual_year_sum:
                    year_offset = sum(
                        [resultat.absdiff for resultat in engine_results]
                    ) / (actual_year_sum * len(engine_results))
                else:
                    year_offset = Decimal(0)
                summary = PersonYearEstimateSummary(
                    person_year=person_year,
                    estimation_engine=engine.__class__.__name__,
                    offset_percent=100 * year_offset,
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

    def _get_data_qs(self, person_year_qs: QuerySet[PersonYear]):
        # Return queryset with one row for each `PersonMonth`.
        # Each row contains PKs for person, person month, and values for year and month.
        # Each row also contains summed values for monthly reported A and B income, as
        # each person month can have one or more A or B incomes reported.

        def sum_amount(field):
            return Sum(Coalesce(F(field), Value(0), output_field=DecimalField()))

        qs = (
            PersonMonth.objects.filter(
                person_year__person__in=person_year_qs.values("person")
            )
            .prefetch_related("monthlyaincomereport_set", "monthlybincomereport_set")
            .values(
                _person_pk=F("person_year__person__pk"),
                _person_month_pk=F("pk"),
                _year=F("person_year__year__year"),
                _month=F("month"),
            )
            .annotate(
                _a_amount=sum_amount("monthlyaincomereport__amount"),
                _b_amount=sum_amount("monthlybincomereport__amount"),
            )
            .order_by(
                "_person_pk",
                "_year",
                "_month",
            )
        )

        return qs

    def _iterate_by_person(
        self, data_qs: QuerySet
    ) -> Iterable[List[Dict[str, int | Decimal]]]:
        # Iterate over `data_qs` and yield a subset of rows for each `_person_pk`
        return (
            list(vals) for key, vals in groupby(data_qs, key=itemgetter("_person_pk"))
        )

    def _get_person_month_for_row(
        self, subset: List[Dict[str, int | Decimal]], year: int, month: int
    ) -> int | None:
        for row in subset:
            if row["_year"] == year and row["_month"] == month:
                return self._person_month_map[row["_person_month_pk"]]
        return None

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
