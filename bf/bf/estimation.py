# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from typing import Iterable, Sequence

from project.util import trim_list_first

from bf.data import MonthlyIncomeData
from bf.models import IncomeEstimate


class EstimationEngine:
    @classmethod
    def estimate(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    @classmethod
    def subset_sum(
        cls, relevant: Iterable[MonthlyIncomeData], year: int, month: int
    ) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        return Decimal(0) + sum([row.amount for row in relevant])


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder - DONE
* Sum af beløbene for de seneste 12 måneder - DONE

"""


class InYearExtrapolationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def estimate(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:
        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(subset, year, month)
        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(relevant_items, year, month)
            omitted_count = month - relevant_count
            year_estimate = (12 - omitted_count) * amount_sum / relevant_count
            return IncomeEstimate(
                estimated_year_result=year_estimate,
                engine=cls.__name__,
            )
        return None

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year: int, month: int
    ) -> Sequence[MonthlyIncomeData]:
        items = [item for item in subset if item.year == year and item.month <= month]
        # Trim off items with no income from the beginning of the list
        items = trim_list_first(items, lambda item: not item.amount.is_zero())
        return items


class TwelveMonthsSummationEngine(EstimationEngine):
    description = "Summation af beløb for de seneste 12 måneder"
    # Styrker: Stabile indkomster, indkomster der har samme mønster hert år
    # Svagheder: Outliers (store indkomster i enkelte måneder)

    @classmethod
    def estimate(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:

        # Do not estimate if there is no data one year back
        if not [x for x in subset if x.month == month and x.year == year - 1]:
            # TODO: How can we decide this better?
            # * of the last 12 months, less than x months contain data?
            # * the month 12 months ago doesn't contain data,
            #   and the month before/after it doesn't either?
            return None

        relevant_items = cls.relevant(subset, year, month)
        year_estimate = cls.subset_sum(relevant_items, year, month)

        return IncomeEstimate(
            estimated_year_result=year_estimate,
            # person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year: int, month: int
    ) -> Iterable[MonthlyIncomeData]:
        items = filter(
            lambda item: (item.year == year and item.month <= month)
            or (item.year == (year - 1) and item.month > month),
            subset,
        )
        return items


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
