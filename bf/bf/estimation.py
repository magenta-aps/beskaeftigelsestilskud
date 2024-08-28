# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from typing import Iterable, Sequence, Tuple

import pmdarima
from project.util import trim_list_first

from bf.data import MonthlyIncomeData
from bf.models import IncomeEstimate, IncomeType


class EstimationEngine:
    @classmethod
    def estimate(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
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
    def classes():
        return EstimationEngine.__subclasses__()

    @staticmethod
    def instances():
        return [cls() for cls in EstimationEngine.classes()]

    @classmethod
    def estimate_ab(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
    ) -> Tuple[IncomeEstimate | None, IncomeEstimate | None]:
        return (
            cls.estimate(subset, year, month, IncomeType.A),
            cls.estimate(subset, year, month, IncomeType.B),
        )


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
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(subset, year, month)
        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(relevant_items, year, month, income_type)
            omitted_count = month - relevant_count
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
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
        income_type: IncomeType,
    ) -> IncomeEstimate | None:

        # Do not estimate if there is no data one year back
        if not [x for x in subset if x.month == month and x.year == year - 1]:
            # TODO: How can we decide this better?
            # * of the last 12 months, less than x months contain data?
            # * the month 12 months ago doesn't contain data,
            #   and the month before/after it doesn't either?
            return None

        relevant_items = cls.relevant(subset, year, month)
        year_estimate = cls.subset_sum(relevant_items, year, month, income_type)

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
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        relevant_items = cls.relevant(subset, year, month)
        amount_sum = cls.subset_sum(relevant_items, year, month, income_type)
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


class SarimaEngine(EstimationEngine):
    description = (
        "Forudsigelse med SARIMA (seasonal autoregressive integrated moving average)"
    )

    @staticmethod
    def get_amount(income_data: MonthlyIncomeData, income_type: IncomeType) -> Decimal:
        if income_type == IncomeType.A:
            return income_data.a_amount
        if income_type == IncomeType.B:
            return income_data.b_amount

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year: int, month: int
    ) -> Sequence[MonthlyIncomeData]:
        items = [
            item
            for item in subset
            if item.year < year or (item.year == year and item.month <= month)
        ]
        # Trim off items with no income from the beginning of the list
        items = trim_list_first(items, lambda item: not item.amount.is_zero())
        return items

    @classmethod
    def estimate(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        all_prior_incomes = [
            cls.get_amount(item, income_type)
            for item in cls.relevant(subset, year, month)
        ]
        this_year_incomes = [
            cls.get_amount(item, income_type)
            for item in filter(
                lambda item: item.year == year, cls.relevant(subset, year, month)
            )
        ]
        remaining_months = 12 - month
        if len(all_prior_incomes) > 12:
            if min(all_prior_incomes) == max(all_prior_incomes):
                # Samme indkomst i hele træningssættet
                # SARIMA smider en warning hvis den fodres med dette
                prediction = [min(all_prior_incomes)] * remaining_months
                this_year_incomes += prediction
            else:
                try:
                    if remaining_months == 0:
                        prediction = []
                    else:
                        try:
                            model = pmdarima.auto_arima(
                                all_prior_incomes, seasonal=True, m=12
                            )
                            prediction = list(model.predict(n_periods=remaining_months))
                        except ValueError:
                            model = pmdarima.auto_arima(
                                all_prior_incomes, seasonal=True, m=12, D=0
                            )
                            prediction = list(model.predict(n_periods=remaining_months))
                except ValueError:
                    # See
                    # http://alkaline-ml.com/pmdarima/seasonal-differencing-issues.html
                    return None
            this_year_incomes += [Decimal(p) for p in prediction]
            year_estimate = sum(this_year_incomes)
            return IncomeEstimate(
                estimated_year_result=year_estimate,
                engine=cls.__name__,
                income_type=income_type,
            )
        return None
