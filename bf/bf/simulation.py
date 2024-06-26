# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data_analysis.models import CalculationResult
from django.db.models import Q

from bf.calculate import CalculationEngine
from bf.models import (
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
class Prediction:
    engine: CalculationEngine
    items: list[PredictionItem]


@dataclass(frozen=True, repr=False)
class SimulationResultRow:
    income_series: list[IncomeItem]
    income_sum: int
    predictions: list[Prediction]


@dataclass(frozen=True)
class SimulationResult:
    rows: list[SimulationResultRow]


class Simulation:
    def __init__(
        self,
        engines: list[CalculationEngine],
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

        actual_year_sum = self.person_year.sum_amount

        income_a = MonthlyAIncomeReport.annotate_year(
            MonthlyAIncomeReport.objects.all()
        )
        income_a = MonthlyAIncomeReport.annotate_month(income_a)
        income_a = income_a.filter(person_month__person_year__person=self.person)

        income_b = MonthlyBIncomeReport.annotate_year(
            MonthlyBIncomeReport.objects.all()
        )
        income_b = MonthlyBIncomeReport.annotate_month(income_b)
        income_b = income_b.filter(person_month__person_year__person=self.person)

        income_series = [
            IncomeItem(year=item.year, month=item.month, value=item.amount)
            for item in list(income_a) + list(income_b)
        ]

        predictions = []

        for engine in self.engines:
            prediction_items = []
            for month in range(1, 13):
                try:
                    person_month = self.person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue
                engine_name = engine.__class__.__name__
                try:
                    calculation_result = CalculationResult.objects.get(
                        person_month=person_month, engine=engine_name
                    )
                except CalculationResult.DoesNotExist:
                    visible_a_reports = income_a.filter(
                        Q(f_year__lt=self.year)
                        | Q(f_year=self.year, f_month__lte=month)
                    )
                    visible_b_reports = income_b.filter(
                        Q(f_year__lt=self.year)
                        | Q(f_year=self.year, f_month__lte=month)
                    )
                    calculation_result = engine.calculate(
                        visible_a_reports, visible_b_reports, person_month
                    )
                    if calculation_result is not None:
                        calculation_result.calculated_year_result = actual_year_sum

                if calculation_result is not None:
                    calculated_year_result = calculation_result.calculated_year_result
                    prediction_items.append(
                        PredictionItem(
                            year=self.year,
                            month=month,
                            predicted_value=calculated_year_result,
                            prediction_difference=calculated_year_result
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (calculation_result.offset * 100)
                                if actual_year_sum != 0
                                else None
                            ),
                        )
                    )
            if prediction_items:
                predictions.append(Prediction(engine=engine, items=prediction_items))

        return SimulationResultRow(
            income_series=income_series,
            income_sum=actual_year_sum,
            predictions=predictions,
        )
