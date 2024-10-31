# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from cProfile import Profile

from django.core.management.base import BaseCommand

from bf.integrations.eskat.client import EskatClient
from bf.integrations.eskat.load import ExpectedIncomeHandler, MonthlyIncomeHandler


class Command(BaseCommand):

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("year", type=int)
        parser.add_argument("type", type=str)
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--month", type=int)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year: int = kwargs["year"]
        month: str | None = kwargs["month"]
        cpr: str | None = kwargs["cpr"]
        typ: str = kwargs["type"].lower()
        client = EskatClient.from_settings()
        if typ == "expectedincome":
            if month is not None:
                print("--month is not relevant when fetching expected income")
            ExpectedIncomeHandler.create_or_update_objects(
                year, client.get_expected_income(year, cpr), self.stdout
            )
        if typ == "monthlyincome":
            MonthlyIncomeHandler.create_or_update_objects(
                year,
                client.get_monthly_income(year, month_from=month, cpr=cpr),
                self.stdout,
            )

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
