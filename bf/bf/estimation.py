# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Sequence, Tuple

import pmdarima
from django.db.models import Sum
from project.util import trim_list_first

from bf.data import MonthlyIncomeData
from bf.exceptions import IncomeTypeUnhandledByEngine
from bf.models import IncomeEstimate, IncomeType, MonthlyBIncomeReport, PersonMonth


class EstimationEngine:

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    description = "Tom superklasse"

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
    def classes() -> List[type[EstimationEngine]]:
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

    valid_income_types: List[IncomeType] = [
        IncomeType.A,
        IncomeType.B,
    ]

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

    valid_income_types: List[IncomeType] = [IncomeType.B]

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
            if person_month.month == 12:
                estimated_year_result = MonthlyBIncomeReport.objects.filter(
                    year=person_month.year,
                    person=person_month.person,
                ).aggregate(sum=Sum("amount"))["sum"] or Decimal(0)
            else:
                estimated_year_result = (
                    assessment.brutto_b_indkomst
                    - assessment.brutto_b_før_erhvervsvirk_indhandling
                )
            return IncomeEstimate(
                estimated_year_result=estimated_year_result,
                engine=cls.__name__,
                person_month=person_month,
                income_type=income_type,
            )
        return None


class SarimaEngine(EstimationEngine):
    description = (
        "Forudsigelse med SARIMA (seasonal autoregressive integrated moving average)"
    )

    models: Dict[int, pmdarima.base.BaseARIMA] = {}

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
        pk: int,
        subset: Sequence[MonthlyIncomeData],
        year: int,
        month: int,
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        min_required_months = 12
        relevant = cls.relevant(subset, year, month)
        if len(relevant) < min_required_months:
            return None
        # Oplist alle de indkomster vi har indtil nu, inkl denne måned
        all_prior_incomes = []
        this_year_incomes = []

        for item in relevant:
            amount = cls.get_amount(item, income_type)
            all_prior_incomes.append(amount)
            if item.year == year:
                this_year_incomes.append(amount)

        remaining_months = 12 - month
        if min(all_prior_incomes) == max(all_prior_incomes):
            # Samme indkomst i hele træningssættet
            # SARIMA smider en warning hvis den fodres med dette
            # Tilføj indkomster for måneder vi mangler op til 12
            prediction = [min(all_prior_incomes)] * remaining_months
            this_year_incomes += prediction
        else:
            # Forudsig indkomst for hver måned i år frem til nytår
            try:
                if remaining_months == 0:
                    prediction = []
                else:
                    try:
                        model = cls.models.get(pk)
                        if model is None:
                            model = pmdarima.auto_arima(
                                all_prior_incomes, seasonal=True, m=12, d=0
                            )
                        else:
                            model.update(all_prior_incomes[-1:])
                        prediction = list(model.predict(n_periods=remaining_months))
                        cls.models[pk] = model
                    except ValueError:
                        # Vi kunne ikke lave en god model, så prøv med en dårligere én
                        model = pmdarima.auto_arima(
                            all_prior_incomes, seasonal=True, m=12, D=0, d=0
                        )
                        prediction = list(model.predict(n_periods=remaining_months))
                        if pk in cls.models:
                            del cls.models[pk]
            except ValueError:
                # See
                # http://alkaline-ml.com/pmdarima/seasonal-differencing-issues.html
                return None
            # Tilføj så vi får en liste af månedsindkomster for i år
            this_year_incomes += [Decimal(p) for p in prediction]
        assert len(this_year_incomes) == 12
        year_estimate = sum(this_year_incomes)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            engine=cls.__name__,
            income_type=income_type,
        )
