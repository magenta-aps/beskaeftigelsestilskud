# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from typing import Dict, List

from project.util import trim_list_first

from bf.models import IncomeEstimate


class EstimationEngine:
    @classmethod
    def estimate(
        cls,
        subset: list[dict[str, int | Decimal]],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    @classmethod
    def subset_sum(cls, relevant: List[Dict[str, int | Decimal]]) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        return Decimal(0) + sum(
            [row["_a_amount"] + row["_b_amount"] for row in relevant]
        )


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder - DONE
* Sum af beløbene for de seneste 12 måneder - DONE

"""


class InYearExtrapolationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"
    # Styrker: Stabile indkomster
    # Svagheder: Outliers (store indkomster i enkelte måneder)

    @classmethod
    def estimate(
        cls,
        subset: list[dict[str, int | Decimal]],
        year: int,
        month: int,
    ) -> IncomeEstimate | None:
        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(subset, year, month)
        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(relevant_items)
            omitted_count = month - relevant_count
            year_estimate = (12 - omitted_count) * amount_sum / relevant_count
            return IncomeEstimate(
                estimated_year_result=year_estimate,
                # person_month=person_month,
                engine=cls.__name__,
            )
        return None

    @classmethod
    def relevant(
        cls, subset: List[Dict[str, int | Decimal]], year: int, month: int
    ) -> List[Dict[str, int | Decimal]]:
        items = [
            row for row in subset if row["_year"] == year and row["_month"] <= month
        ]
        # Trim off items with no income from the beginning of the list
        items = trim_list_first(
            items,
            lambda item: not (
                item["_a_amount"].is_zero() and item["_b_amount"].is_zero()
            ),
        )
        return items


class TwelveMonthsSummationEngine(EstimationEngine):
    description = "Summation af beløb for de seneste 12 måneder"
    # Styrker: Stabile indkomster, indkomster der har samme mønster hert år
    # Svagheder: Outliers (store indkomster i enkelte måneder)

    @classmethod
    def estimate(
        cls,
        subset: list,
        year: int,
        month: int,
    ) -> IncomeEstimate | None:

        # Do not estimate if there is no data one year back
        if not [x for x in subset if x["_month"] == month and x["_year"] == year - 1]:
            # TODO: How can we decide this better?
            # * of the last 12 months, less than x months contain data?
            # * the month 12 months ago doesn't contain data,
            #   and the month before/after it doesn't either?
            return None

        relevant_items = cls.relevant(subset, year, month)
        year_estimate = cls.subset_sum(relevant_items)

        return IncomeEstimate(
            estimated_year_result=year_estimate,
            # person_month=person_month,
            engine=cls.__name__,
        )

    @classmethod
    def relevant(
        cls, subset: List[Dict[str, int | Decimal]], year: int, month: int
    ) -> List[Dict[str, int | Decimal]]:
        items = [
            row
            for row in subset
            if (
                (row["_year"] == year and row["_month"] <= month)
                or (row["_year"] == (year - 1) and row["_month"] > month)
            )
        ]
        return items
