# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class MonthlyIncomeData:
    month: int
    year: int
    a_amount: Decimal
    b_amount: Decimal
    person_pk: int
    person_month_pk: int

    @property
    def amount(self):
        return self.a_amount + self.b_amount


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
        "SameAsLastMonthEngine",
        "Ekstrapolation af beløb for den seneste måned",
    ),
    (
        "SelfReportedEngine",
        "Estimering udfra forskudsopgørelsen",
    ),
)

engine_keys = tuple([key for key, desc in engine_choices])
