# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from django.template.defaultfilters import register
from django.utils.formats import number_format
from django.utils.translation import gettext as _

from suila.models import PersonMonth


@register.inclusion_tag("suila/templatetags/amount.html")
def display_amount(person_month: PersonMonth) -> dict:

    if hasattr(person_month, "prismebatchitem"):
        return {"value": format_amount(person_month.benefit_transferred)}
    else:
        return {"value": format_amount(person_month.benefit_calculated)}


@register.filter
def format_amount(
    amount: int | float | Decimal | None,
    decimal_pos: int = 0,
) -> str:
    if amount is None:
        return _("-")
    formatted_amount: str = number_format(
        amount,
        decimal_pos=decimal_pos,
        use_l10n=True,
        force_grouping=True,
    )
    return _("%(amount)s kr." % {"amount": formatted_amount})
