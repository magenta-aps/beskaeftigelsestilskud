from dataclasses import dataclass

from django.db.models import Avg, Q, QuerySet, Sum

from bf.models import MonthIncome


class CalculationEngine:
    pass


@dataclass
class CalculationResult:
    year_prediction: int


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder
* Sum af beløbene for de seneste 12 måneder

"""


class InYearExtrapolationEngine(CalculationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende year"

    @classmethod
    def calculate(cls, datapoints: QuerySet[MonthIncome]) -> CalculationResult:
        year = datapoints.order_by("-year", "-month").values_list("year", flat=True)[0]
        year_prediction = int(
            12 * datapoints.filter(year=year).aggregate(avg=Avg("amount"))["avg"]
        )
        return CalculationResult(year_prediction=year_prediction)


class TwelveMonthsSummationEngine(CalculationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def calculate(cls, datapoints: QuerySet[MonthIncome]) -> CalculationResult:
        latest = datapoints.order_by("-year", "-month")[0]
        relevant = datapoints.filter(
            Q(year=latest.year, month__lte=latest.month)
            | Q(year=latest.year - 1, month__gt=latest.month)
        )
        year_prediction = int(relevant.aggregate(sum=Sum("amount"))["sum"])
        return CalculationResult(year_prediction=year_prediction)
