# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from django.db.models import QuerySet
from project.util import int_divide_end

from suila.estimation import EstimationEngine
from suila.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    WorkingTaxCreditCalculationMethod,
)


@dataclass(slots=True)
class IncomeItemValuePart:
    income_type: IncomeType
    value: Decimal


@dataclass(slots=True)
class IncomeItem:
    year: int
    month: int
    value: Decimal
    value_parts: List[IncomeItemValuePart]


@dataclass(frozen=True, slots=True)
class PredictionItem:
    year: int
    month: int
    predicted_value: Decimal
    prediction_difference: Decimal
    prediction_difference_pct: Decimal | None


@dataclass(frozen=True, slots=True)
class PayoutItem:
    year: int
    month: int
    payout: Decimal
    cumulative_payout: Decimal
    correct_payout: Decimal
    estimated_year_result: Decimal
    estimated_year_benefit: Decimal


@dataclass(frozen=True, slots=True)
class Prediction:
    engine: EstimationEngine
    items: list[PredictionItem]


@dataclass(frozen=True, repr=False, slots=True)
class SimulationResultRow:
    income_sum: Dict[int, Decimal]
    predictions: list[Prediction]
    title: str
    chart_type: Literal["line", "bar"] = "line"


@dataclass(frozen=True, repr=False, slots=True)
class IncomeRow:
    income_series: list[IncomeItem]
    title: str
    chart_type: Literal["line", "bar"] = "line"


@dataclass(frozen=True, repr=False, slots=True)
class SingleDatasetRow:
    points: Sequence[Tuple[int | Decimal, int | Decimal]]


@dataclass(frozen=True, repr=False, slots=True)
class PayoutRow:
    payout: list[PayoutItem]
    title: str
    chart_type: Literal["line", "bar"] = "line"


@dataclass(frozen=True, slots=True)
class SimulationResult:
    rows: list[SimulationResultRow | IncomeRow]
    year_start: int
    year_end: int


class Simulation:
    def __init__(
        self,
        engines: list[EstimationEngine],
        person: Person,
        year_start: int | None,
        year_end: int | None,
        income_type: IncomeType | None,
        calculation_methods: Dict[int, WorkingTaxCreditCalculationMethod] | None = None,
    ):
        if year_end is None:
            year_end = date.today().year
        if year_start is None:
            year_start = year_end
        self.engines = engines
        self.person = person
        self.year_start = year_start
        self.year_end = year_end
        self.income_type = income_type
        self.person_years: QuerySet[PersonYear] = person.personyear_set.filter(
            year__year__gte=year_start, year__year__lte=year_end
        )
        self.result = SimulationResult(
            rows=[self.income()]
            + [self.payout()]
            + [self.prediction(engine) for engine in self.engines],
            year_start=year_start,
            year_end=year_end,
        )
        self.calculation_methods = (
            {
                key: SingleDatasetRow(points=calculation_method.graph_points)
                for key, calculation_method in calculation_methods.items()
                if calculation_method
            }
            if calculation_methods
            else None
        )

    def actual_year_sum(self, income_type) -> Dict[int, Decimal]:
        year_sum = {}
        for person_year in self.person_years:
            year_sum[person_year.year.year] = person_year.amount_sum_by_type(
                income_type
            )
        return year_sum

    def income(self):
        income_series: Dict[tuple, IncomeItem] = {}

        if self.income_type in (IncomeType.A, None):
            for item in list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    a_income__gt=0,
                )
            ):
                income_series = self._monthly_income_report_to_income_series(
                    income_series, IncomeType.A, item
                )

        if self.income_type in (IncomeType.B, None):

            # Add any income from assessment
            for person_year in self.person_years:
                year = person_year.year.year

                if not person_year.b_income:
                    continue

                income_series = self._yearly_monthly_income_to_income_series(
                    income_series,
                    IncomeType.B,
                    person_year.b_income - person_year.b_expenses,
                    year,
                )

        if self.income_type in (IncomeType.U, None):
            for item in list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    u_income__gt=0,
                )
            ):
                income_series = self._monthly_income_report_to_income_series(
                    income_series, IncomeType.U, item
                )

        income_series_list = list(income_series.values())
        income_series_list.sort(
            key=lambda item: (
                item.year,
                item.month,
            )
        )

        return IncomeRow(
            title="Månedlig indkomst",
            income_series=income_series_list,
            chart_type="bar",
        )

    def payout(self):
        payout_items = []
        for person_year in self.person_years:
            cumulative_payout = Decimal(0)
            for month in range(1, 13):
                b_result = person_year.b_income - person_year.b_expenses
                a_result = Decimal(0)
                try:
                    person_month = person_year.personmonth_set.get(month=month)
                    payout = person_month.benefit_paid or Decimal(0)
                    actual_year_benefit = person_month.actual_year_benefit
                    a_result = (
                        person_month.estimated_year_result or Decimal(0)
                    ) - person_year.catchsale_expenses
                    estimated_year_result = a_result + b_result
                    estimated_year_benefit = person_month.estimated_year_benefit

                except PersonMonth.DoesNotExist:
                    payout = Decimal(0)
                    estimated_year_result = a_result + b_result
                    actual_year_benefit = (
                        person_year.year.calculation_method.calculate_float(
                            estimated_year_result
                        )
                    )
                    estimated_year_benefit = actual_year_benefit
                cumulative_payout += payout
                payout_items.append(
                    PayoutItem(
                        year=person_year.year.year,
                        month=month,
                        payout=payout,
                        cumulative_payout=cumulative_payout,
                        correct_payout=actual_year_benefit,
                        estimated_year_result=estimated_year_result,
                        estimated_year_benefit=estimated_year_benefit,
                    )
                )
        return PayoutRow(title="Månedlig udbetaling", payout=payout_items)

    def prediction(self, engine: EstimationEngine):

        income_type = self.income_type

        if income_type is None:  # None means to show both in view
            if IncomeType.A not in engine.valid_income_types:
                income_type = IncomeType.B
            elif IncomeType.B not in engine.valid_income_types:
                income_type = IncomeType.A

        # NOTE: 'value_parts' is currently set to an empty array, since it was
        # implemented in `self.income()`. The fields purpose is to show all the
        # different values that make up the 'value'-field. It have just not been
        # implemented in this method yet.

        estimates: List[Prediction] = []
        prediction_items = []
        actual_year_sums = self.actual_year_sum(income_type)
        actual_year_results = {}
        engine_name = engine.__class__.__name__
        for year in range(self.year_start, self.year_end + 1):
            try:
                person_year = self.person_years.get(year=year)
            except PersonYear.DoesNotExist:
                continue
            actual_year_sum = actual_year_sums[year]
            actual_year_sum -= person_year.b_expenses
            actual_year_sum -= person_year.catchsale_expenses
            for month in range(1, 13):
                try:
                    person_month = person_year.personmonth_set.get(month=month)
                except PersonMonth.DoesNotExist:
                    continue
                estimate_qs = IncomeEstimate.objects.filter(
                    person_month=person_month,
                    engine=engine_name,
                )
                if income_type is not None:
                    estimate_qs = estimate_qs.filter(
                        income_type=income_type,
                    )
                if estimate_qs.exists():
                    # Add Decimal(0) to shut MyPy up
                    estimated_year_result = Decimal(0) + sum(
                        [estimate.estimated_year_result for estimate in estimate_qs]
                    )
                    if income_type in (None, IncomeType.B):
                        estimated_year_result += (
                            person_year.b_income
                            - person_year.b_expenses
                            - person_year.catchsale_expenses
                        )
                    offset = IncomeEstimate.qs_offset(estimate_qs)
                    prediction_items.append(
                        PredictionItem(
                            year=year,
                            month=month,
                            predicted_value=estimated_year_result,
                            prediction_difference=estimated_year_result
                            - actual_year_sum,
                            prediction_difference_pct=(
                                (offset * 100) if actual_year_sum != 0 else None
                            ),
                        )
                    )
            actual_year_results[year] = actual_year_sum

        if prediction_items:
            estimates.append(Prediction(engine=engine, items=prediction_items))

        return SimulationResultRow(
            title=engine.__class__.__name__ + " - " + engine.description,
            income_sum=actual_year_results,
            predictions=estimates,
        )

    def _monthly_income_report_to_income_series(
        self,
        income_series: Dict[tuple, IncomeItem],
        income_type: IncomeType,
        item: MonthlyIncomeReport,
    ) -> Dict[tuple, IncomeItem]:
        value_part: Optional[IncomeItemValuePart] = None

        income_value_attr = "a_income"
        if income_type == IncomeType.B:
            income_value_attr = "b_income"
        elif income_type == IncomeType.U:
            income_value_attr = "u_income"

        if not hasattr(item, income_value_attr):
            raise ValueError(
                f"item does not have income_value_attr: {income_value_attr}"
            )
        income_value = getattr(item, income_value_attr)

        value_part = IncomeItemValuePart(income_type=income_type, value=income_value)
        if (item.year, item.month) not in income_series:
            income_series[(item.year, item.month)] = IncomeItem(
                year=item.year,
                month=item.month,
                value=income_value,
                value_parts=[value_part] if value_part else [],
            )
        else:
            income_series[(item.year, item.month)].value += income_value

            if value_part:
                income_series[(item.year, item.month)].value_parts.append(value_part)

        return income_series

    def _yearly_monthly_income_to_income_series(
        self,
        income_series: Dict[tuple, IncomeItem],
        income_type: IncomeType,
        income_value: Decimal,
        year: int,
    ) -> Dict[tuple, IncomeItem]:
        monthly_income = int_divide_end(int(income_value), 12)
        for month in range(1, 13):
            income_item_value_part = IncomeItemValuePart(
                income_type=income_type,
                value=Decimal(monthly_income[month - 1]),
            )

            if not income_item_value_part.value:
                continue

            income_item = income_series.get((year, month))
            if income_item is None:
                income_series[(year, month)] = IncomeItem(
                    year=year,
                    month=month,
                    value=income_item_value_part.value,
                    value_parts=[income_item_value_part],
                )
            else:
                income_series_new_ref = income_series[(year, month)]
                income_series_new_ref.value += income_item_value_part.value
                income_series_new_ref.value_parts.append(income_item_value_part)

        return income_series
