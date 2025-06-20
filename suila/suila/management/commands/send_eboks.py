# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from itertools import batched

from django.conf import settings
from django.db.models import Q

from suila.integrations.eboks.client import EboksClient
from suila.management.commands.common import SuilaBaseCommand
from suila.models import PersonMonth, PersonYear, SuilaEboksMessage, TaxScope


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--save", action="store_true")
        parser.add_argument("--send", action="store_true")
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        client = EboksClient.from_settings()
        year = kwargs["year"]
        month = kwargs["month"]
        save = kwargs["save"]
        send = kwargs["send"]

        qs = (
            PersonYear.objects.filter(
                year_id=year,
                person__welcome_letter_sent_at__isnull=True,
                tax_scope=TaxScope.FULDT_SKATTEPLIGTIG,
                person__full_address__isnull=False,
            )
            .exclude(
                person__full_address="",
            )
            .exclude(
                Q(person__full_address="0")
                | Q(person__full_address__contains="9999")
                | Q(person__full_address__contains="Ukendt")
                | Q(person__full_address__contains="Administrativ")
            )
        )
        if kwargs.get("cpr"):
            qs = qs.filter(person__cpr=kwargs["cpr"])
        qs = qs.select_related("person")

        def handle_person_year(personyear: PersonYear):
            typ = (
                "afventer"
                if settings.ENFORCE_QUARANTINE  # type: ignore
                and personyear.in_quarantine
                else "opgørelse"
            )
            try:
                personmonth: PersonMonth = personyear.personmonth_set.get(month=month)
                suilamessage = SuilaEboksMessage.objects.create(
                    person_month=personmonth, type=typ
                )
                if save:
                    with open(f"/tmp/{personyear.person.cpr}.pdf", "wb") as fp:
                        fp.write(suilamessage.pdf)
                return suilamessage
            except PersonMonth.DoesNotExist:
                pass

        i = 0
        for batch in batched(qs.iterator(), 100):
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(handle_person_year, personyear)
                    for personyear in batch
                ]
                for future in as_completed(futures):
                    suilamessage = future.result()
                    if suilamessage:
                        if send:
                            suilamessage.send(client)
                        suilamessage.update_welcome_letter()
                    i += 1
                    self.stdout.write(str(i))
