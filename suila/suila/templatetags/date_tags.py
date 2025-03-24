# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from datetime import date

from django.template.defaultfilters import register
from django.utils import dates
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from suila.dates import get_payment_date as _get_payment_date
from suila.models import PersonMonth

logger = logging.getLogger(__name__)

# Include the English month names in the Suila source code to make them available for
# translating into Greenlandic (`django.utils.dates.MONTHS` uses the English names as
# source texts.)
_("January")
_("February")
_("March")
_("April")
_("May")
_("June")
_("July")
_("August")
_("September")
_("October")
_("November")
_("December")

# Include the English short alternative month names (`django.utils.dates.MONTHS_ALT`)
# in the Suila source code to make them available for translating into Greenlandic.
# These month names are used by the `value|date` template filter when using the custom
# `DATE_FORMAT` for the `kl` locale.
pgettext_lazy("alt. month", "January")
pgettext_lazy("alt. month", "February")
pgettext_lazy("alt. month", "March")
pgettext_lazy("alt. month", "April")
pgettext_lazy("alt. month", "May")
pgettext_lazy("alt. month", "June")
pgettext_lazy("alt. month", "July")
pgettext_lazy("alt. month", "August")
pgettext_lazy("alt. month", "September")
pgettext_lazy("alt. month", "October")
pgettext_lazy("alt. month", "November")
pgettext_lazy("alt. month", "December")


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
