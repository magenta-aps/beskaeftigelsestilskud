# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from typing import Iterator

from suila.integrations.eskat.client import EskatClient
from suila.integrations.eskat.load import (
    AnnualIncomeHandler,
    ExpectedIncomeHandler,
    MonthlyIncomeHandler,
    TaxInformationHandler,
)
from suila.management.commands.common import SuilaBaseCommand
from suila.models import DataLoad


class Command(SuilaBaseCommand):
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

        self._write_verbose("EskatClient initializing...")
        client = EskatClient.from_settings()

        self._write_verbose("Creating DataLoad instance in DB...")
        load = DataLoad.objects.create(
            source="eskat",
            parameters={"year": year, "month": month, "cpr": cpr, "typ": typ},
        )

        self._write_verbose(
            f"Handling subcommand: {typ} (YEAR={year}, MONTH={month}, CPR={cpr})"
        )
        if typ == "annualincome":
            if month is not None:
                self.stdout.write(
                    "--month is not relevant when fetching expected income"
                )
            AnnualIncomeHandler.create_or_update_objects(
                client.get_annual_income(year, cpr), load, self.stdout
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
            for year_, month_kwargs in self._get_year_and_month_kwargs(year, month):
                self._write_verbose(
                    (
                        "- Fetching monthly_income "
                        f"from {month_kwargs["month_from"]}/{year_} "
                        f"to {month_kwargs["month_to"]}/{year_}..."
                    )
                )
                monthly_income_data = client.get_monthly_income(
                    year_, cpr=cpr, **month_kwargs
                )
                self._write_verbose(
                    f"\t- MonthlyIncome-entries fetched: {len(monthly_income_data)}"
                )

                MonthlyIncomeHandler.create_or_update_objects(
                    year_,
                    monthly_income_data,
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

    def _get_year_and_month_kwargs(
        self,
        year: int,
        month: int | None,
        num: int = 3,
        offset: int = 2,
    ) -> Iterator[tuple[int, dict]]:
        def ym(offset: int) -> tuple[int, int]:
            assert isinstance(month, int)
            div: int
            mod: int
            div, mod = divmod(month - num - offset, 12)
            y: int = year + div
            m: int = mod + 1
            return y, m

        if month is None:
            month = date.today().month

        assert 1 <= month <= 12

        start_year, start_month = ym(offset)
        end_year, end_month = ym(0)

        if start_year == end_year:
            yield start_year, {"month_from": start_month, "month_to": end_month}
        else:
            yield start_year, {"month_from": start_month, "month_to": 12}
            yield end_year, {"month_from": 1, "month_to": end_month}
