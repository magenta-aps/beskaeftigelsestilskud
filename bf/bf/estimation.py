# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from typing import Iterable

from bf.data import MonthlyIncomeData
from bf.models import IncomeEstimate


class EstimationEngine:
    @classmethod
    def estimate(
        cls,
        # a_reports: QuerySet[MonthlyAIncomeReport],  # A income
        # b_reports: QuerySet[MonthlyBIncomeReport],  # B income
        # person_month: PersonMonth,
        subset: Iterable[MonthlyIncomeData],
        year: int,
        month: int,
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
        # a_reports: QuerySet[MonthlyAIncomeReport],
        # b_reports: QuerySet[MonthlyBIncomeReport],
        # person_month: PersonMonth,
        subset: Iterable[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:
        # year = person_month.year
        # month = person_month.month
        # amount_sum = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
        #     b_reports, year, month
        # )
        amount_sum = cls.subset_sum(subset, year, month)
        year_estimate = int(12 * (amount_sum / month))
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            # person_month=person_month,
            engine=cls.__name__,
        )

    # @classmethod
    # def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
    #     # Do not use any properties on the class as annotation names.
    #     # Django will explode trying to put values into the properties.
    #     qs = qs.filter(year=year, month__in=range(1, month + 1))
    #     # print(qs.explain())
    #     return MonthlyIncomeReport.sum_queryset(qs)

    @classmethod
    def subset_sum(
        cls, subset: Iterable[MonthlyIncomeData], year: int, month: int
    ) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        return Decimal(0) + sum(
            [
                item.amount
                for item in subset
                if item.year == year and item.month <= month
            ]
        )


class TwelveMonthsSummationEngine(EstimationEngine):
    description = "Summation af beløb for de seneste 12 måneder"

    @classmethod
    def estimate(
        cls,
        # a_reports: QuerySet[MonthlyAIncomeReport],
        # b_reports: QuerySet[MonthlyBIncomeReport],
        # person_month: PersonMonth,
        subset: Iterable[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:

        # year = person_month.year
        # month = person_month.month
        # year_estimate = cls.queryset_sum(a_reports, year, month) + cls.queryset_sum(
        #     b_reports, year, month
        # )
        year_estimate = cls.subset_sum(subset, year, month)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            # person_month=person_month,
            engine=cls.__name__,
        )

    # @classmethod
    # def queryset_sum(cls, qs: QuerySet, year: int, month: int) -> Decimal:
    #     # Do not use any properties on the class as annotation names.
    #     # Django will explode trying to put values into the properties.
    #     qs = qs.filter(
    #         Q(year=year, month__in=range(1, month + 1))
    #         | Q(year=year - 1, month__in=range(month + 1, 13))
    #     )
    #     return MonthlyIncomeReport.sum_queryset(qs)

    @classmethod
    def subset_sum(
        cls, subset: Iterable[MonthlyIncomeData], year: int, month: int
    ) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        return Decimal(0) + sum(
            [
                item.amount
                for item in subset
                if (
                    (item.year == year and item.month <= month)
                    or (item.year == (year - 1) and item.month > month)
                )
            ]
        )


class SameAsLastMonthEngine(EstimationEngine):
    description = "Ekstrapolation af beløb baseret udelukkende på den foregående måned"

    @classmethod
    def estimate(
        cls, subset: Iterable[MonthlyIncomeData], year: int, month: int
    ) -> IncomeEstimate | None:
        amount_sum = cls.subset_sum(subset, year, month)
        year_estimate = int(12 * amount_sum)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            engine=cls.__name__,
        )

    @classmethod
    def subset_sum(
        cls, subset: Iterable[MonthlyIncomeData], year: int, month: int
    ) -> Decimal:

        for item in subset:
            if item.year == year and item.month == month:
                return Decimal(item.amount)
        return Decimal(0)
