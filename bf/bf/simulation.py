# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict

from django.db.models import QuerySet

from bf.estimation import EstimationEngine
from bf.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
)


@dataclass(frozen=True)
class IncomeItem:
    year: int
    month: int
    value: Decimal


@dataclass(frozen=True)
class PredictionItem:
    year: int
    month: int
    predicted_value: int
    prediction_difference: Decimal
    prediction_difference_pct: Decimal


@dataclass(frozen=True)
class PayoutItem:
    year: int
    month: int
    payout: Decimal
    correct_payout: Decimal


@dataclass(frozen=True)
class Prediction:
    engine: EstimationEngine
    items: list[PredictionItem]


@dataclass(frozen=True, repr=False)
class SimulationResultRow:
    income_sum: int
    predictions: list[Prediction]
    title: str
    payout: list[PayoutItem]


@dataclass(frozen=True, repr=False)
class IncomeRow:
    income_series: list[IncomeItem]
    title: str


@dataclass(frozen=True)
class SimulationResult:
    rows: list[SimulationResultRow | IncomeRow]
    year_start: int
    year_end: int


class Simulation:
    def __init__(
        self,
        engines: list[EstimationEngine],
        person: Person,
        year_start: int | None,
        year_end: int | None,
        income_type: IncomeType | None,
    ):
        if year_end is None:
            year_end = date.today().year
        if year_start is None:
            year_start = year_end
        self.engines = engines
        self.person = person
        self.year_start = year_start
        self.year_end = year_end
        self.income_type = income_type
        self.person_years: QuerySet[PersonYear] = person.personyear_set.filter(
            year__year__gte=year_start, year__year__lte=year_end
        )
        self.result = SimulationResult(
            rows=[self.income()] + [self.prediction(engine) for engine in self.engines],
            year_start=year_start,
            year_end=year_end,
        )

    def actual_year_sum(self) -> Dict[int, Decimal]:
        year_sum = {}
        for person_year in self.person_years:
            year_sum[person_year.year.year] = person_year.amount_sum_by_type(
                self.income_type
            )
        return year_sum

    def income(self):
        income = []
        if self.income_type in (IncomeType.A, None):
            income += list(
                MonthlyAIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                )
            )
        if self.income_type in (IncomeType.B, None):
            income += list(
                MonthlyBIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                )
            )

        income_series_build = defaultdict(lambda: Decimal(0))
        for item in income:
            income_series_build[(item.year, item.month)] += item.amount
        income_series = [
            IncomeItem(year=year, month=month, value=amount)
            for (year, month), amount in income_series_build.items()
        ]
        income_series.sort(
            key=lambda item: (
                item.year,
                item.month,
            )
        )
        return IncomeRow(
            title="Månedlig indkomst",
            income_series=income_series,
        )

    def prediction(self, engine: EstimationEngine):

        income = []
        if self.income_type in (IncomeType.A, None):
            income += list(
                MonthlyAIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                )
            )
        if self.income_type in (IncomeType.B, None):
            income += list(
                MonthlyBIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                )
            )

        income_series_build = defaultdict(lambda: Decimal(0))
        for item in income:
            income_series_build[(item.year, item.month)] += item.amount
        income_series = [
            IncomeItem(year=year, month=month, value=amount)
            for (year, month), amount in income_series_build.items()
        ]
        income_series.sort(
            key=lambda item: (
                item.year,
                item.month,
            )
        )

        estimates = []
        prediction_items = []
        actual_year_sums = self.actual_year_sum()
        engine_name = engine.__class__.__name__
        for year in range(self.year_start, self.year_end + 1):
            person_year = self.person_years.get(year=year)
            actual_year_sum = actual_year_sums[year]
            for month in range(1, 13):
                try:
                    person_month = person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue
                estimate_qs = IncomeEstimate.objects.filter(
                    person_month=person_month,
                    engine=engine_name,
                )
                if self.income_type is not None:
                    estimate_qs = estimate_qs.filter(
                        income_type=self.income_type,
                    )

                if estimate_qs.exists():
                    estimated_year_result = sum(
                        [estimate.estimated_year_result for estimate in estimate_qs]
                    )
                    offset = IncomeEstimate.qs_offset(estimate_qs)
                    prediction_items.append(
                        PredictionItem(
                            year=year,
                            month=month,
                            predicted_value=estimated_year_result,
                            prediction_difference=estimated_year_result
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (offset * 100) if actual_year_sum != 0 else None
                            ),
                        )
                    )

            payout_items = []
            payout = 0
            for month in range(1, 13):
                try:
                    person_month = person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue

                if person_month.benefit_paid:
                    payout += person_month.benefit_paid

                payout_items.append(
                    PayoutItem(
                        year=year,
                        month=month,
                        payout=payout,
                        correct_payout=person_month.actual_year_benefit,
                    )
                )
        if prediction_items:
            estimates.append(Prediction(engine=engine, items=prediction_items))

        return SimulationResultRow(
            title=engine.__class__.__name__,
            income_sum=actual_year_sums,  # TODO: brug rigtigt i js
            predictions=estimates,
            payout=payout_items,
        )
