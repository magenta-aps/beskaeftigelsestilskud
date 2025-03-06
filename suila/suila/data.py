# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class MonthlyIncomeData:
    month: int
    year: int
    a_income: Decimal
    u_income: Decimal
    person_pk: int
    person_month_pk: int
    person_year_pk: int
    b_income: Decimal = Decimal(0)

    @property
    def amount(self) -> Decimal:
        return Decimal(self.a_income + self.u_income)

    @property
    def year_month(self) -> date:
        return date(self.year, self.month, 1)


engine_choices = (
    # We could create this list with [
    #     (cls.__name__, cls.description)
    #     for cls in EstimationEngine.__subclasses__()
    # ]
    # but that would make a circular import
    (
        "InYearExtrapolationEngine",
        "Ekstrapolation af beløb for måneder i indeværende år",
    ),
    (
        "TwelveMonthsSummationEngine",
        "Summation af beløb for de seneste 12 måneder",
    ),
    (
        "TwoYearSummationEngine",
        "Summation af beløb for de seneste 24 måneder",
    ),
    (
        "MonthlyContinuationEngine",
        "Ekstrapolation af beløb for den seneste måned",
    ),
    (
        "SelfReportedEngine",
        "Estimering udfra forskudsopgørelsen",
    ),
)

engine_keys = tuple([key for key, desc in engine_choices])
