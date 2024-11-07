# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging

from django.template.defaultfilters import register
from django.utils import dates

logger = logging.getLogger(__name__)


@register.filter
def month_name(month: int) -> str:
    # Return localized month name abbreviation (0 -> "Jan", 5 -> "Maj", etc.)
    try:
        return dates.MONTHS[month].capitalize()
    except KeyError:
        logger.error("could not return month name for month=%r", month)
    except Exception:
        logger.exception("unexpected error")
