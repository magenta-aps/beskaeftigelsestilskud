# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from django.db.models import QuerySet
from project.util import int_divide_end

from bf.estimation import EstimationEngine
from bf.models import (
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
    value_parts: Optional[List[IncomeItemValuePart]] = None


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
        incomes_monthly: List[IncomeItemValuePart] = []

        if self.income_type in (IncomeType.A, None):
            incomes_monthly += list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    a_income__gt=0,
                )
            )
        if self.income_type in (IncomeType.B, None):
            incomes_monthly += list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    b_income__gt=0,
                )
            )

        income_series_new: Dict[tuple, IncomeItem] = {}
        for item in incomes_monthly:
            if (item.year, item.month) not in income_series_new:
                income_series_new[(item.year, item.month)] = IncomeItem(
                    year=item.year,
                    month=item.month,
                    value=item.a_income + item.b_income,
                    value_parts=[],
                )
            else:
                income_series_new[(item.year, item.month)].value += (
                    item.a_income + item.b_income
                )

            if item.a_income:
                income_series_new[(item.year, item.month)].value_parts.append(
                    IncomeItemValuePart(income_type=IncomeType.A, value=item.a_income)
                )

            if item.b_income:
                income_series_new[(item.year, item.month)].value_parts.append(
                    IncomeItemValuePart(income_type=IncomeType.B, value=item.b_income)
                )

        # Add any income from final settelment / yearly
        if self.income_type in (IncomeType.B, IncomeType.U, None):
            for person_year in self.person_years:
                year = person_year.year.year

                for yearly_income_field in ["b_income", "u_income"]:
                    if not hasattr(person_year, yearly_income_field):
                        continue

                    yearly_income_value = getattr(person_year, yearly_income_field)

                    # Skip calculations for incomes which are None
                    if yearly_income_value is None:
                        continue

                    if yearly_income_field == "b_income":
                        yearly_income_field_type = IncomeType.B
                    elif yearly_income_field == "u_income":
                        yearly_income_field_type = IncomeType.U
                    else:
                        raise ValueError(
                            (
                                "invalid 'yearly_income_field' "
                                f"value: {yearly_income_field}"
                            )
                        )

                    # Divide by 12. Spread the remainder over the last months
                    monthly_income = int_divide_end(int(yearly_income_value), 12)
                    for month in range(1, 13):
                        income_item_value_part = IncomeItemValuePart(
                            income_type=yearly_income_field_type,
                            value=Decimal(monthly_income[month - 1]),
                        )

                        if not income_item_value_part.value:
                            continue

                        income_item = income_series_new.get((year, month))
                        if income_item is None:
                            income_series_new[(year, month)] = IncomeItem(
                                year=year,
                                month=month,
                                value=income_item_value_part.value,
                                value_parts=[income_item_value_part],
                            )
                        else:
                            income_series_new[
                                (year, month)
                            ].value += income_item_value_part.value

                            income_series_new[(year, month)].value_parts.append(
                                income_item_value_part
                            )

        income_series_list = list(income_series_new.values())
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
            for person_month in person_year.personmonth_set.order_by("month"):
                payout = person_month.benefit_paid or Decimal(0)
                cumulative_payout += payout
                payout_items.append(
                    PayoutItem(
                        year=person_year.year.year,
                        month=person_month.month,
                        payout=payout,
                        cumulative_payout=cumulative_payout,
                        correct_payout=person_month.actual_year_benefit,
                        estimated_year_result=person_month.estimated_year_result,
                        estimated_year_benefit=person_month.estimated_year_benefit,
                    )
                )
        return PayoutRow(title="Månedlig udbetaling", payout=payout_items)

    def prediction(self, engine: EstimationEngine):

        income: List[MonthlyIncomeReport] = []
        income_type = self.income_type

        if income_type is None:  # None means to show both in view
            if IncomeType.A not in engine.valid_income_types:
                income_type = IncomeType.B
            elif IncomeType.B not in engine.valid_income_types:
                income_type = IncomeType.A

        if income_type in (IncomeType.A, None):
            income += list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    a_income__gt=0,
                )
            )
        if income_type in (IncomeType.B, None):
            income += list(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__person=self.person,
                    person_month__person_year__year__gte=self.year_start,
                    person_month__person_year__year__lte=self.year_end,
                    b_income__gt=0,
                )
            )

        income_series_build: Dict[Tuple[int, int], Decimal] = defaultdict(
            lambda: Decimal(0)
        )
        for item in income:
            income_series_build[(item.year, item.month)] += (
                item.a_income + item.b_income
            )
        income_series = [
            IncomeItem(year=year, month=month, value=amount)
            for (year, month), amount in income_series_build.items()
        ]
        income_series.sort(
            key=lambda item: (
                item.year,
                item.month,
            )
        )

        estimates = []
        prediction_items = []
        actual_year_sums = self.actual_year_sum(income_type)
        engine_name = engine.__class__.__name__
        for year in range(self.year_start, self.year_end + 1):
            try:
                person_year = self.person_years.get(year=year)
            except PersonYear.DoesNotExist:
                continue
            actual_year_sum = actual_year_sums[year]
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

        if prediction_items:
            estimates.append(Prediction(engine=engine, items=prediction_items))

        return SimulationResultRow(
            title=engine.__class__.__name__ + " - " + engine.description,
            income_sum=actual_year_sums,
            predictions=estimates,
        )
