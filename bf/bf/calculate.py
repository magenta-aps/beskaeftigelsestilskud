# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from data_analysis.models import CalculationResult
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from bf.models import (
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    MonthlyIncomeReport,
    PersonMonth,
)


class CalculationEngine:
    @classmethod
    def calculate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],  # A income
        b_reports: QuerySet[MonthlyBIncomeReport],  # B income
        person_month: PersonMonth,
    ) -> CalculationResult | None:
        raise NotImplementedError


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder
* Sum af beløbene for de seneste 12 måneder

"""


class InYearExtrapolationEngine(CalculationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def calculate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],
        b_reports: QuerySet[MonthlyBIncomeReport],
        person_month: PersonMonth,
    ) -> CalculationResult | None:
        if not a_reports.exists() and not b_reports.exists():
            return None
        year = person_month.year
        month = person_month.month
        amount_sum = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
            b_reports, year, month
        )
        year_prediction = int(12 * (amount_sum / month))
        return CalculationResult(
            calculated_year_result=year_prediction,
            person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
        # Do not use any properties on the class as annotation names.
        # Django will explode trying to put values into the properties.
        qs = MonthlyIncomeReport.annotate_month(qs)
        qs = MonthlyIncomeReport.annotate_year(qs)
        qs = qs.filter(f_year=year, f_month__lte=month)
        return qs.aggregate(sum=Coalesce(Sum("amount"), Decimal(0)))["sum"]


class TwelveMonthsSummationEngine(CalculationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def calculate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],
        b_reports: QuerySet[MonthlyBIncomeReport],
        person_month: PersonMonth,
    ) -> CalculationResult | None:
        if not a_reports.exists() and not b_reports.exists():
            return None
        year = person_month.year
        month = person_month.month
        year_prediction = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
            b_reports, year, month
        )
        return CalculationResult(
            calculated_year_result=year_prediction,
            person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
        # Do not use any properties on the class as annotation names.
        # Django will explode trying to put values into the properties.
        qs = MonthlyIncomeReport.annotate_month(qs)
        qs = MonthlyIncomeReport.annotate_year(qs)
        qs = qs.filter(
            Q(f_year=year, f_month__lte=month) | Q(f_year=year - 1, f_month__gt=month)
        )
        return qs.aggregate(sum=Coalesce(Sum("amount"), Decimal(0)))["sum"]
