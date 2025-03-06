# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from dateutil.relativedelta import TU, relativedelta


def get_payment_date(year: int, month: int) -> date:
    # The "official" payment date is the third Tuesday two months after the month
    # specified via the `year` and `month` arguments.
    # E.g. if `year` and `month` specifies February 2025, the official payment date is
    # April 15, 2025.
    return date(year, month, 1) + relativedelta(months=2, weekday=TU(+3))
