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
