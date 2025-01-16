# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.core.management import call_command
from django.core.management.base import BaseCommand

from suila.benefit import get_payout_date
from suila.management.commands.job_dispatcher import Command as JobDispatcherCommand
from suila.models import JobLog, Person, PrismeAccountAlias, PrismeBatchItem


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("cpr", type=str)
        # parser.add_argument("--year", type=int)
        # parser.add_argument("--month", type=int)
        parser.add_argument("--reraise", action="store_true", default=False)
        super().add_arguments(parser)

    def handle(self, *args, **kwargs):
        self._cpr = kwargs["cpr"]
        self._reraise = kwargs["reraise"]
        self._command = JobDispatcherCommand()
        self._payout_date = get_payout_date(2024, 1)

        # Remove previous Prisme batch items
        qs = PrismeBatchItem.objects.filter(
            person_month__person_year__person__cpr=self._cpr
        )
        qs.delete()

        # Temporarily link all 2025 Prisme account aliases to tax year 2024
        PrismeAccountAlias.objects.filter(tax_year=2025).update(tax_year=2024)

        # Pretend we have retrieved a location code for the person under test.
        # Normally this is handled via `get_person_info_from_dafo`.
        Person.objects.update_or_create(
            cpr=self._cpr, defaults={"location_code": "961"}
        )

        # Remove previous job logs for this CPR
        JobLog.objects.all().delete()

        # 0. Autoselect estimation engine
        call_command(
            self._command,
            reraise=self._reraise,
            cpr=self._cpr,
            year=self._payout_date.year,
            month=1,
            day=1,
        )

        # 1. Load input data; estimate income; calculate benefits
        call_command(
            self._command,
            reraise=self._reraise,
            cpr=self._cpr,
            year=self._payout_date.year,
            month=self._payout_date.month,
            day=self._payout_date.day - 2,
        )

        # 2. Export benefits
        call_command(
            self._command,
            reraise=self._reraise,
            cpr=self._cpr,
            year=self._payout_date.year,
            month=self._payout_date.month,
            day=self._payout_date.day - 1,
        )

        qs = PrismeBatchItem.objects.filter(
            person_month__person_year__person__cpr=self._cpr
        )
        for item in qs.order_by("pk"):
            print(item.prisme_batch.export_date)
            print(item.prisme_batch.status)
            print(item.g68_content)
            print(item.g69_content)
            print()

        # Undo
        PrismeAccountAlias.objects.filter(tax_year=2024).update(tax_year=2025)
