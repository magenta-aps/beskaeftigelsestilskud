# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import F, Q, Sum

from bf.calculate import CalculationEngine
from bf.models import ASalaryReport, Employer, Person


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
    employer: Employer
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
        year: int = date.today().year,
    ):
        self.engines = engines
        self.person = person
        self.year = year
        self.result = SimulationResult(rows=list(self._run()))

    def _run(self):
        qs = ASalaryReport.objects.alias(
            person=F("person_month__person_year__person"),
            year=F("person_month__person_year__year"),
            month=F("person_month__month"),
        ).filter(person=self.person.pk)
        employers = [x.employer for x in qs.distinct("employer")]
        for employer in employers:
            employment = qs.filter(employer=employer)
            actual_year_sum = employment.filter(year=self.year).aggregate(
                s=Sum("amount")
            )["s"]

            income_series = [
                IncomeItem(year=item.year, month=item.month, value=item.amount)
                for item in employment
            ]

            predictions = []

            for engine in self.engines:
                prediction_items = []
                for month in range(1, 13):
                    visible_datapoints = employment.filter(
                        Q(year__lt=self.year) | Q(year=self.year, month__lte=month)
                    )
                    resultat = engine.calculate(visible_datapoints)
                    prediction_items.append(
                        PredictionItem(
                            year=self.year,
                            month=month,
                            predicted_value=resultat.year_prediction,
                            prediction_difference=resultat.year_prediction
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (
                                    abs(
                                        (resultat.year_prediction - actual_year_sum)
                                        / actual_year_sum
                                    )
                                    * 100
                                )
                                if actual_year_sum != 0
                                else None
                            ),
                        )
                    )

                predictions.append(Prediction(engine=engine, items=prediction_items))

            yield SimulationResultRow(
                employer=employer,
                income_series=income_series,
                income_sum=actual_year_sum,
                predictions=predictions,
            )
