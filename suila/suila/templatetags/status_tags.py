# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from common.utils import add_working_days
from django.template.defaultfilters import register
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from suila.dates import get_payment_date
from suila.models import PersonMonth, PrismeBatchItem


def is_awaiting_payment_transfer(
    person_month: PersonMonth,
    margin_days: int = 2,
) -> bool:
    """Return True if the given person month's benefit is currently awaiting transfer to
    the bank account of the citizen. Otherwise, return False.
    """
    # Suila reads daily posting status updates from Prisme (in
    # `load_prisme_benefits_posting_status`.) There is usually a short period where the
    # posting status is defined in Prisme (and in Suila), but the benefit is not yet
    # visible to the recipient in their bank account. During that period, Suila should
    # continue to show the status "Beløb fastlagt" in order to avoid user confusion.
    # We add a margin of 2 days (`margin_days`) to the payment date to give a little
    # extra buffer for things to "settle" between Prisme, NemKonto, and individual bank
    # IT systems.
    payment_date = get_payment_date(person_month.year, person_month.month)
    margin_date = add_working_days(payment_date, margin_days)
    today = datetime.date.today()
    # Find out if we are still not past the margin date
    if today <= margin_date:
        return True
    return False


@register.inclusion_tag("suila/templatetags/status.html")
def display_status(person_month: PersonMonth) -> dict:
    try:
        posting_status = PrismeBatchItem.PostingStatus(
            person_month.prismebatchitem.status  # type: ignore
        )

        paused = person_month.prismebatchitem.paused

    except PrismeBatchItem.DoesNotExist:
        # TODO: show "Afventer udbetaling" if estimated year result is between 475000
        # and 500000 kr.
        # TODO: show "Årsopgørelse er sendt" if a Suila-tapit "årsopgørelse" has been
        # generated and sent to the person.
        if datetime.date.today() < person_month.year_month:
            return {"name": _("Foreløbigt beløb"), "established": False}
        else:
            if person_month.paused:
                return {"name": _("Udbetalingspause"), "established": True}
            else:
                return {"name": _("Beløb fastlagt"), "established": True}
    else:
        if paused:
            return {"name": _("Udbetalingspause"), "established": True}
        elif person_month.benefit_transferred == 0:
            return {"name": _("Beløb fastlagt"), "established": True}
        elif is_awaiting_payment_transfer(person_month):
            return {"name": _("Beløb fastlagt"), "established": True}
        else:
            return {"name": posting_status.label, "established": True}


@register.filter
def format_tax_scope(tax_scope: str) -> StrOrPromise:
    if tax_scope == "FULL":
        return _("Fuld skattepligtig")
    elif tax_scope == "LIM":
        return _("Delvist skattepligtig")
    elif tax_scope is None:
        return _("Ikke i mandtal")
    return ""
