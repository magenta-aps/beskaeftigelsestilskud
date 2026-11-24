# SPDX-FileCopyrightText: 2026 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from itertools import batched
from typing import List

from django.core.management import call_command

from suila.integrations.eskat.client import EskatClient
from suila.integrations.eskat.load import AnnualIncomeHandler
from suila.management.commands.common import SuilaBaseCommand
from suila.models import AnnualIncome, DataLoad


class Command(SuilaBaseCommand):
    def _handle(self):
        current_year = date.today().year
        for year in range(current_year - 5, current_year + 1):
            updated_annual_incomes: List[AnnualIncome] = self.fetch_annual_income(year)
            for annual_income in updated_annual_incomes:

                # Genberegn tilskud for det pågældende skatteår
                # evt. ved kørsel af jobbet calculate_benefit:
                person_year = annual_income.person_year
                for month in range(1, 13):
                    call_command(
                        "calculate_benefit",
                        person_year.year.year,
                        month,
                        person_year.person.cpr,
                    )

            # Opret nye årsopgørelser
            # evt. ved kørsel af jobbet generate_final_settlements:
            ids = list(
                AnnualIncome.objects.filter(pk__in=updated_annual_incomes).values_list(
                    "person_year__person_id", flat=True
                )
            )
            for chunk in batched(ids, 50):
                call_command("generate_final_settlements", year, ids=chunk)

    def fetch_annual_income(self, year) -> List[AnnualIncome]:
        fetch_chunk_size = 20
        insert_chunk_size = 50

        client = EskatClient.from_settings()
        load = DataLoad.objects.create(
            source="eskat",
            parameters={"year": year, "typ": "annualincome"},
        )

        annual_income_data = client.get_annual_income(
            year, None, chunk_size=fetch_chunk_size
        )
        changed: List[AnnualIncome] = []
        for chunk in batched(annual_income_data, insert_chunk_size):
            changed += AnnualIncomeHandler.create_or_update_objects(
                chunk, load, self.stdout
            )
        return changed

    def fetch_annual_income_alternative(self, year) -> List[AnnualIncome]:
        latest_load = DataLoad.objects.order_by("-pk").first()
        call_command("load_eskat", year, "annualincome")
        new_load = DataLoad.objects.get(pk__gt=latest_load.pk)
        return list(AnnualIncome.objects.filter(load=new_load))
