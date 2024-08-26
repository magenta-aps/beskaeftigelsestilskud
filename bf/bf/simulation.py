# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from bf.estimation import EstimationEngine
from bf.models import (
    IncomeEstimate,
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
    ):
        if year is None:
            year = date.today().year
        self.engines = engines
        self.person = person
        self.year = year
        self.person_year: PersonYear = person.personyear_set.get(year__year=year)
        self.result = SimulationResult(rows=[self._run()])

    def _run(self):
        actual_year_sum = self.person_year.amount_sum

        income_a = MonthlyAIncomeReport.objects.filter(
            person=self.person,
            person_month__person_year__year=self.year,
        )
        income_b = MonthlyBIncomeReport.objects.filter(
            person=self.person,
            person_month__person_year__year=self.year,
        )

        income_series = [
            IncomeItem(year=item.year, month=item.month, value=item.amount)
            for item in list(income_a) + list(income_b)
        ]

        estimates = []

        for engine in self.engines:
            prediction_items = []
            for month in range(1, 13):
                try:
                    person_month = self.person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue
                engine_name = engine.__class__.__name__
                try:
                    estimate = IncomeEstimate.objects.get(
                        person_month=person_month, engine=engine_name
                    )
                except IncomeEstimate.DoesNotExist:
                    continue

                if estimate is not None:
                    estimated_year_result = estimate.estimated_year_result
                    prediction_items.append(
                        PredictionItem(
                            year=self.year,
                            month=month,
                            predicted_value=estimated_year_result,
                            prediction_difference=estimated_year_result
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (estimate.offset * 100)
                                if actual_year_sum != 0
                                else None
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
