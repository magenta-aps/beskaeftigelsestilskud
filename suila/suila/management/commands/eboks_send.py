# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.conf import settings

from suila.integrations.eboks.client import EboksClient
from suila.integrations.eboks.message import SuilaEboksMessage
from suila.management.commands.common import SuilaBaseCommand
from suila.models import PersonMonth, PersonYear, TaxScope


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    welcome_letter = "opgørelse"

    def _handle(self, *args, **kwargs):
        client = EboksClient.from_settings()
        year = kwargs["year"]
        month = kwargs["month"]

        qs = PersonYear.objects.filter(
            year_id=year,
            person__welcome_letter_sent_at__isnull=True,
            tax_scope=TaxScope.FULDT_SKATTEPLIGTIG,
        )
        if kwargs.get("cpr"):
            qs = qs.filter(person__cpr=kwargs["cpr"])
        qs = qs.select_related("person")

        for personyear in qs:
            typ = (
                "afventer"
                if settings.ENFORCE_QUARANTINE and personyear.in_quarantine
                else "opgørelse"
            )
            try:
                personmonth: PersonMonth = personyear.personmonth_set.get(month=month)
                suilamessage = SuilaEboksMessage.objects.create(
                    person_month=personmonth, type=typ
                )
                suilamessage.send(client)
                suilamessage.update_welcome_letter()
            except PersonMonth.DoesNotExist:
                pass
