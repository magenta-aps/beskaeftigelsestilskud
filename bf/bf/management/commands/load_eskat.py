# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from bf.integrations.eskat.client import EskatClient
from bf.integrations.eskat.load import (
    AnnualIncomeHandler,
    ExpectedIncomeHandler,
    MonthlyIncomeHandler,
    TaxInformationHandler,
)
from bf.management.commands.common import BfBaseCommand
from bf.models import DataLoad


class Command(BfBaseCommand):
    filename = __file__

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("type", type=str)
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--month", type=int)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year: int = kwargs["year"]
        month: str | None = kwargs["month"]
        cpr: str | None = kwargs["cpr"]
        typ: str = kwargs["type"].lower()
        client = EskatClient.from_settings()
        load = DataLoad.objects.create(
            source="eskat",
            parameters={"year": year, "month": month, "cpr": cpr, "typ": typ},
        )
        if typ == "annualincome":
            if month is not None:
                self.stdout.write(
                    "--month is not relevant when fetching expected income"
                )
            AnnualIncomeHandler.create_or_update_objects(
                year, client.get_annual_income(year, cpr), load, self.stdout
            )
        if typ == "expectedincome":
            if month is not None:
                self.stdout.write(
                    "--month is not relevant when fetching expected income"
                )
            ExpectedIncomeHandler.create_or_update_objects(
                year, client.get_expected_income(year, cpr), load, self.stdout
            )
        if typ == "monthlyincome":
            MonthlyIncomeHandler.create_or_update_objects(
                year,
                client.get_monthly_income(year, month_from=month, cpr=cpr),
                load,
                self.stdout,
            )
        if typ == "taxinformation":
            TaxInformationHandler.create_or_update_objects(
                year,
                client.get_tax_information(year, cpr=cpr),
                load,
                self.stdout,
            )
