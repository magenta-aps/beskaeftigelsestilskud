from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import F, Q, QuerySet, Sum

from bf.calculate import (
    CalculationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import ASalaryReport, Employer, Person


@dataclass(frozen=True)
class IncomeItem:
    year: int
    month: int
    value: Decimal


@dataclass(frozen=True)
class PredictionItem:
    month: int
    predicted_value: int
    prediction_difference: Decimal
    prediction_difference_pct: Decimal


@dataclass(frozen=True, repr=False)
class SimulationResultRow:
    person: Person
    employer: Employer
    income_series: list[IncomeItem]
    income_sum: int
    engine: CalculationEngine
    predictions: list[PredictionItem]


@dataclass(frozen=True)
class SimulationResult:
    rows: list[SimulationResultRow]


class Simulation:
    def __init__(
        self,
        engines: list[CalculationEngine],
        person_qs: QuerySet[Person] = None,
        year: int = date.today().year,
    ):
        self._person_qs = person_qs or Person.objects.all()
        self._engines = engines
        self._year = year
        self.result = SimulationResult(rows=list(self._run()))

    def _run(self):
        for person in self._person_qs:
            qs = ASalaryReport.objects.alias(
                person=F("person_month__person_year__person"),
                year=F("person_month__person_year__year"),
                month=F("person_month__month"),
            ).filter(person=person.pk)
            employers = [x.employer for x in qs.distinct("employer")]
            for employer in employers:
                employment = qs.filter(employer=employer)
                actual_year_sum = employment.filter(year=self._year).aggregate(
                    s=Sum("amount")
                )["s"]

                income_series = [
                    IncomeItem(year=item.year, month=item.month, value=item.amount)
                    for item in employment
                ]

                for engine in self._engines:
                    predictions = []
                    for month in range(1, 13):
                        visible_datapoints = employment.filter(
                            Q(year__lt=self._year)
                            | Q(year=self._year, month__lte=month)
                        )
                        resultat = engine.calculate(visible_datapoints)
                        predictions.append(
                            PredictionItem(
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

                    yield SimulationResultRow(
                        person=person,
                        employer=employer,
                        income_series=income_series,
                        income_sum=actual_year_sum,
                        engine=engine,
                        predictions=predictions,
                    )


sim = Simulation(
    [InYearExtrapolationEngine(), TwelveMonthsSummationEngine()],
    Person.objects.all(),
    year=2024,
)
