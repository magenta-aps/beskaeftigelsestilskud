# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from data_analysis.models import IncomeEstimate
from django.db.models import Q, QuerySet

from bf.models import (
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    MonthlyIncomeReport,
    PersonMonth,
)


class EstimationEngine:
    @classmethod
    def estimate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],  # A income
        b_reports: QuerySet[MonthlyBIncomeReport],  # B income
        person_month: PersonMonth,
    ) -> IncomeEstimate | None:
        raise NotImplementedError


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder
* Sum af beløbene for de seneste 12 måneder

"""


class InYearExtrapolationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def estimate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],
        b_reports: QuerySet[MonthlyBIncomeReport],
        person_month: PersonMonth,
    ) -> IncomeEstimate | None:
        year = person_month.year
        month = person_month.month
        amount_sum = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
            b_reports, year, month
        )
        year_estimate = int(12 * (amount_sum / month))
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
        # Do not use any properties on the class as annotation names.
        # Django will explode trying to put values into the properties.
        qs = qs.filter(year=year, month__in=range(1, month + 1))
        # print(qs.explain())
        return MonthlyIncomeReport.sum_queryset(qs)


class TwelveMonthsSummationEngine(EstimationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def estimate(
        cls,
        a_reports: QuerySet[MonthlyAIncomeReport],
        b_reports: QuerySet[MonthlyBIncomeReport],
        person_month: PersonMonth,
    ) -> IncomeEstimate | None:

        year = person_month.year
        month = person_month.month
        year_estimate = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
            b_reports, year, month
        )
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
        # Do not use any properties on the class as annotation names.
        # Django will explode trying to put values into the properties.
        qs = qs.filter(
            Q(year=year, month__in=range(1, month + 1))
            | Q(year=year - 1, month__in=range(month + 1, 13))
        )
        return MonthlyIncomeReport.sum_queryset(qs)
