# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from bf.models import ASalaryReport
from data_analysis.models import CalculationResult
from django.db.models import Avg, F, Max, Q, QuerySet, Sum


class CalculationEngine:
    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult | None:
        raise NotImplementedError


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder
* Sum af beløbene for de seneste 12 måneder

"""


class InYearExtrapolationEngine(CalculationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult | None:
        if not datapoints.exists():
            return None
        datapoints = datapoints.annotate(
            # Do not use any properties on the class as annotation names.
            # Django will explode trying to put values into the properties.
            f_year=F("person_month__person_year__year"),
            f_month=F("person_month__month"),
        )
        year = datapoints.order_by("-f_year", "-f_month").values_list(
            "f_year", flat=True
        )[0]
        relevant: QuerySet[ASalaryReport] = datapoints.filter(f_year=year).order_by(
            "f_month"
        )
        year_prediction = int(12 * relevant.aggregate(avg=Avg("amount"))["avg"])
        latest: ASalaryReport = relevant.last()  # type: ignore
        latest.calculated_year_result = year_prediction
        latest.save(update_fields=("calculated_year_result",))
        return CalculationResult(year_prediction=year_prediction, a_salary_report=latest, engine=cls.__name__)


class TwelveMonthsSummationEngine(CalculationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def calculate(cls, datapoints: QuerySet[ASalaryReport]) -> CalculationResult | None:
        if not datapoints.exists():
            return None
        datapoints = datapoints.annotate(
            f_year=F("person_month__person_year__year"),
            f_month=F("person_month__month"),
        )
        latest_year = datapoints.aggregate(max_year=Max("f_year"))["max_year"]
        latest_month = datapoints.filter(f_year=latest_year).aggregate(
            max_month=Max("f_month")
        )["max_month"]
        relevant: QuerySet[ASalaryReport] = datapoints.filter(
            Q(f_year=latest_year, f_month__lte=latest_month)
            | Q(f_year=latest_year - 1, f_month__gt=latest_month)
        ).order_by("f_year", "f_month")
        year_prediction = int(relevant.aggregate(sum=Sum("amount"))["sum"])
        latest: ASalaryReport = relevant.last()  # type: ignore
        latest.calculated_year_result = year_prediction
        latest.save(update_fields=("calculated_year_result",))
        return CalculationResult(year_prediction=year_prediction, a_salary_report=latest, engine=cls.__name__)
