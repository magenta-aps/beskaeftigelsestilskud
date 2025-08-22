# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from dateutil.relativedelta import TU, relativedelta

from suila.models import PersonMonth


def get_payment_date(year: int, month: int) -> date:
    # The "official" payment date is the third Tuesday two months after the month
    # specified via the `year` and `month` arguments.
    # E.g. if `year` and `month` specifies February 2025, the official payment date is
    # April 15, 2025.
    return date(year, month, 1) + relativedelta(months=2, weekday=TU(+3))


def get_pause_effect_date(person_month: PersonMonth):
    """
    Returns the date on which a pause becomes effective
    """
    # Advance to the last month with a prismebatchitem
    while hasattr(person_month, "prismebatchitem") and person_month.next:
        person_month = person_month.next

    year = person_month.person_year.year.year
    month = person_month.month

    # If current month has a prismebatchitem, move to next month
    if hasattr(person_month, "prismebatchitem"):
        month += 1
        if month > 12:
            month = 1
            year += 1

    return get_payment_date(year, month)
