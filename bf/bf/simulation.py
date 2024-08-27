# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
    income_series: list[IncomeItem]
    income_sum: int
    predictions: list[Prediction]
    payout: list[PayoutItem]


@dataclass(frozen=True)
class SimulationResult:
    rows: list[SimulationResultRow]


class Simulation:
    def __init__(
        self,
        engines: list[EstimationEngine],
        person: Person,
        year: int | None,
        income_type: IncomeType | None,
    ):
        if year is None:
            year = date.today().year
        self.engines = engines
        self.person = person
        self.year = year
        self.income_type = income_type
        self.person_year: PersonYear = person.personyear_set.get(year__year=year)
        self.result = SimulationResult(rows=[self._run()])

    def _run(self):
        actual_year_sum = self.person_year.amount_sum_by_type(self.income_type)
        income = []
        if self.income_type in (IncomeType.A, None):
            income += list(
                MonthlyAIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year=self.year,
                )
            )
        if self.income_type in (IncomeType.B, None):
            income += list(
                MonthlyBIncomeReport.objects.filter(
                    person=self.person,
                    person_month__person_year__year=self.year,
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
        for engine in self.engines:
            prediction_items = []
            for month in range(1, 13):
                try:
                    person_month = self.person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue
                engine_name = engine.__class__.__name__
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
                            year=self.year,
                            month=month,
                            predicted_value=estimated_year_result,
                            prediction_difference=estimated_year_result
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (offset * 100) if actual_year_sum != 0 else None
                            ),
                        )
                    )

            if prediction_items:
                estimates.append(Prediction(engine=engine, items=prediction_items))

        payout_items = []
        payout = 0
        for month in range(1, 13):
            try:
                person_month = self.person_year.personmonth_set.get(month=month)
            except PersonMonth.DoesNotExist:
                continue

            if person_month.benefit_paid:
                payout += person_month.benefit_paid

            payout_items.append(
                PayoutItem(
                    year=self.year,
                    month=month,
                    payout=payout,
                    correct_payout=person_month.actual_year_benefit,
                )
            )

        return SimulationResultRow(
            income_series=income_series,
            income_sum=actual_year_sum,
            predictions=estimates,
            payout=payout_items,
        )
