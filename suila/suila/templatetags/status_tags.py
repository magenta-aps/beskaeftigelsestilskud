# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from django.template.defaultfilters import register
from django.utils.translation import gettext_lazy as _

from suila.models import PersonMonth, PrismeBatchItem


@register.inclusion_tag("suila/templatetags/status.html")
def display_status(person_month: PersonMonth) -> dict:
    try:
        posting_status = PrismeBatchItem.PostingStatus(
            person_month.prismebatchitem.status  # type: ignore
        )
    except PrismeBatchItem.DoesNotExist:
        if datetime.date.today() < person_month.year_month:
            return {"name": _("Afventer"), "established": False}
        else:
            return {"name": _("Fastlagt"), "established": True}
    else:
        return {"name": posting_status.label, "established": True}
