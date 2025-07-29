# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from django.template.defaultfilters import register
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from suila.models import PersonMonth, PrismeBatchItem, TaxScope


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
        else:
            return {"name": posting_status.label, "established": True}


@register.filter
def format_tax_scope(tax_scope: str) -> StrOrPromise:
    if tax_scope in (TaxScope.FULDT_SKATTEPLIGTIG, "FULL"):
        return _("Fuld skattepligtig")
    elif tax_scope in (TaxScope.DELVIST_SKATTEPLIGTIG, "LIM"):
        return _("Delvist skattepligtig")
    elif tax_scope in (TaxScope.FORSVUNDET_FRA_MANDTAL, None):
        return _("Ikke i mandtal")
    return ""
