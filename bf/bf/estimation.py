# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Sequence, Tuple

from project.util import trim_list_first

from bf.data import MonthlyIncomeData
from bf.exceptions import IncomeTypeUnhandledByEngine
from bf.models import IncomeEstimate, IncomeType, PersonMonth


class EstimationEngine:

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    @classmethod
    def subset_sum(
        cls,
        relevant: Iterable[MonthlyIncomeData],
        year: int,
        month: int,
        income_type: IncomeType,
    ) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        if income_type == IncomeType.A:
            return Decimal(0) + sum([row.a_amount for row in relevant])
        if income_type == IncomeType.B:
            return Decimal(0) + sum([row.b_amount for row in relevant])

    @staticmethod
    def classes() -> List[type]:
        return EstimationEngine.__subclasses__()

    @staticmethod
    def instances() -> List["EstimationEngine"]:
        return [cls() for cls in EstimationEngine.classes()]

    @classmethod
    def estimate_ab(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
    ) -> Tuple[IncomeEstimate | None, IncomeEstimate | None]:
        return (
            cls.estimate(person_month, subset, IncomeType.A),
            cls.estimate(person_month, subset, IncomeType.B),
        )

    valid_income_types = (
        IncomeType.A,
        IncomeType.B,
    )

    @staticmethod
    def valid_engines_for_incometype(income_type: IncomeType):
        return [
            cls
            for cls in EstimationEngine.classes()
            if income_type in cls.valid_income_types
        ]


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
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(subset, person_month.year, person_month.month)
        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(
                relevant_items, person_month.year, person_month.month, income_type
            )
            omitted_count = person_month.month - relevant_count
            year_estimate = (12 - omitted_count) * amount_sum / relevant_count
            return IncomeEstimate(
                estimated_year_result=year_estimate,
                engine=cls.__name__,
                income_type=income_type,
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
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:

        # Do not estimate if there is no data one year back
        if not [
            x
            for x in subset
            if x.month == person_month.month and x.year == person_month.year - 1
        ]:
            # TODO: How can we decide this better?
            # * of the last 12 months, less than x months contain data?
            # * the month 12 months ago doesn't contain data,
            #   and the month before/after it doesn't either?
            return None

        relevant_items = cls.relevant(subset, person_month.year, person_month.month)
        year_estimate = cls.subset_sum(
            relevant_items, person_month.year, person_month.month, income_type
        )

        return IncomeEstimate(
            estimated_year_result=year_estimate,
            # person_month=person_month,
            engine=cls.__name__,
            income_type=income_type,
        )

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year: int, month: int
    ) -> Sequence[MonthlyIncomeData]:
        return list(
            filter(
                lambda item: (item.year == year and item.month <= month)
                or (item.year == (year - 1) and item.month > month),
                subset,
            )
        )


class SameAsLastMonthEngine(EstimationEngine):
    description = "Ekstrapolation af beløb baseret udelukkende på den foregående måned"

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        relevant_items = cls.relevant(subset, person_month.year, person_month.month)
        amount_sum = cls.subset_sum(
            relevant_items, person_month.year, person_month.month, income_type
        )
        year_estimate = int(12 * amount_sum)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            engine=cls.__name__,
            income_type=income_type,
        )

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year: int, month: int
    ) -> Sequence[MonthlyIncomeData]:
        return list(
            filter(
                lambda item: (item.year == year and item.month == month),
                subset,
            )
        )


class SelfReportedEngine(EstimationEngine):
    description = "Estimering udfra forskudsopgørelsen. Kun B-indkomst."

    valid_income_types = (IncomeType.B,)

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        if income_type != IncomeType.B:
            raise IncomeTypeUnhandledByEngine(income_type, cls)
        assessment = person_month.person_year.assessments.order_by("-created").first()
        if assessment is not None:
            return IncomeEstimate(
                estimated_year_result=assessment.erhvervsindtægter_sum,
                engine=cls.__name__,
                income_type=income_type,
            )
