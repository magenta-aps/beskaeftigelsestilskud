# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import calendar
from datetime import date

import holidays
from dateutil.relativedelta import relativedelta

from suila.models import PersonMonth


def get_last_working_day(year: int, month: int) -> date:
    """
    Returns the last working day for a given month
    """
    holiday_calendar = holidays.GL()  # type: ignore

    # Start from the last day of the month
    day_to_return = date(year, month, calendar.monthrange(year, month)[1])

    # Go backwards until we find a working day
    while not holiday_calendar.is_working_day(day_to_return):
        day_to_return -= relativedelta(days=1)

    return day_to_return


def get_payment_date(year: int, month: int) -> date:
    # The "official" payment date is the last working day two months after the month
    # specified via the `year` and `month` arguments.
    # E.g. if `year` and `month` specifies February 2025, the official payment date is
    # April 30, 2025.
    if month <= 10:
        return get_last_working_day(year, month + 2)
    else:
        return get_last_working_day(year + 1, month - 12 + 2)


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
