# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from itertools import batched
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
        parser.add_argument("--skew", action="store_true")
        parser.add_argument("--fetch_chunk_size", type=int, default=20)
        parser.add_argument("--insert_chunk_size", type=int, default=50)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year: int = kwargs["year"]
        month: str | None = kwargs["month"]
        cpr: str | None = kwargs["cpr"]
        typ: str = kwargs["type"].lower()
        skew: bool = kwargs.get("skew", False)
        fetch_chunk_size = kwargs["fetch_chunk_size"]
        insert_chunk_size = kwargs["insert_chunk_size"]

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
            annual_income_data = client.get_annual_income(
                year, cpr, chunk_size=fetch_chunk_size
            )
            for chunk in batched(annual_income_data, insert_chunk_size):
                print(f"Handling parsed chunk of size {len(chunk)}")
                AnnualIncomeHandler.create_or_update_objects(chunk, load, self.stdout)
        if typ == "expectedincome":
            if month is not None:
                self.stdout.write(
                    "--month is not relevant when fetching expected income"
                )
            expected_income_data = client.get_expected_income(
                year, cpr, chunk_size=fetch_chunk_size
            )
            for chunk in batched(expected_income_data, insert_chunk_size):
                print(f"Handling parsed chunk of size {len(chunk)}")
                ExpectedIncomeHandler.create_or_update_objects(
                    year, chunk, load, self.stdout
                )
        if typ == "monthlyincome":
            if skew:
                year_months = self._get_year_and_month_kwargs(year, month)
            else:
                year_months = [(year, {"month_from": None, "month_to": None})]
            for year_, month_kwargs in year_months:
                if month_kwargs["month_from"] is None:
                    self._write_verbose(f"- Fetching monthly_income for {year_}")
                else:
                    self._write_verbose(
                        (
                            "- Fetching monthly_income "
                            f'from {month_kwargs["month_from"]}/{year_} '
                            f'to {month_kwargs["month_to"]}/{year_}...'
                        )
                    )
                monthly_income_data = client.get_monthly_income(
                    year_, cpr=cpr, chunk_size=fetch_chunk_size, **month_kwargs
                )
                # monthly_income_data er en Generator der kommer med MonthlyIncome
                # objekter fra eskat. Størrelsen af chunks vi vælger her er
                # uafhængig af størrelsen på chunks vi henter fra eskat.
                # (eskat fylder i en pulje med én skestørrelse,
                # vi tager af puljen med en anden skestørrelse)
                for chunk in batched(monthly_income_data, insert_chunk_size):
                    # Spis af generatoren i chunks
                    print(f"Handling parsed chunk of size {len(chunk)}")
                    MonthlyIncomeHandler.create_or_update_objects(
                        year_,
                        chunk,
                        load,
                        self.stdout,
                    )
        if typ == "taxinformation":
            tax_information_data = client.get_tax_information(
                year, cpr=cpr, chunk_size=fetch_chunk_size
            )
            for chunk in batched(tax_information_data, insert_chunk_size):
                # Spis af generatoren i chunks
                print(f"Handling parsed chunk of size {len(chunk)}")
                TaxInformationHandler.create_or_update_objects(
                    year,
                    chunk,
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
