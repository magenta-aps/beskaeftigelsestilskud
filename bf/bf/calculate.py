from dataclasses import dataclass

from django.db.models import Avg, F, Max, Q, QuerySet, Sum

from bf.models import ASalaryReport


@dataclass
class CalculationResult:
    year_prediction: int


class CalculationEngine:
    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult:
        raise NotImplementedError


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder
* Sum af beløbene for de seneste 12 måneder

"""


class InYearExtrapolationEngine(CalculationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult:
        datapoints = datapoints.annotate(
            year=F("person_month__person_year__year"), month=F("person_month__month")
        )
        year = datapoints.order_by("-year", "-month").values_list("year", flat=True)[0]
        year_prediction = int(
            12 * datapoints.filter(year=year).aggregate(avg=Avg("amount"))["avg"]
        )
        return CalculationResult(year_prediction=year_prediction)


class TwelveMonthsSummationEngine(CalculationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult:
        datapoints = datapoints.annotate(
            year=F("person_month__person_year__year"), month=F("person_month__month")
        )
        latest_year = datapoints.aggregate(max_year=Max("year"))["max_year"]
        latest_month = datapoints.filter(year=latest_year).aggregate(
            max_month=Max("month")
        )["max_month"]
        relevant = datapoints.filter(
            Q(year=latest_year, month__lte=latest_month)
            | Q(year=latest_year - 1, month__gt=latest_month)
        )
        year_prediction = int(relevant.aggregate(sum=Sum("amount"))["sum"])
        return CalculationResult(year_prediction=year_prediction)
