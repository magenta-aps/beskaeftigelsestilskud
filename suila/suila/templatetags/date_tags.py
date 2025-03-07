# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from datetime import date

from django.template.defaultfilters import register
from django.utils import dates

from suila.dates import get_payment_date as _get_payment_date
from suila.models import PersonMonth

logger = logging.getLogger(__name__)


@register.filter
def month_name(month: int) -> str | None:
    # Return localized month name abbreviation (0 -> "Jan", 5 -> "Maj", etc.)
    try:
        return dates.MONTHS[month].capitalize()
    except KeyError:
        logger.error("could not return month name for month=%r", month)
    except Exception:
        logger.exception("unexpected error")
    return None


@register.filter
def get_payment_date(person_month: PersonMonth) -> date:
    return _get_payment_date(person_month.year, person_month.month)
