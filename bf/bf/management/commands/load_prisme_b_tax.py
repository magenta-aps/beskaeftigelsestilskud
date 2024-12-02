# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from django.core.management.base import BaseCommand

from bf.integrations.prisme.b_tax import BTaxPaymentImport


class Command(BaseCommand):
    def add_arguments(self, parser):
        today = date.today()
        parser.add_argument(
            "--year",
            type=int,
            nargs="?",
            default=today.year,
        )
        parser.add_argument(
            "--month",
            type=int,
            nargs="?",
            default=today.month,
        )

    def handle(self, *args, **options):
        b_tax_import: BTaxPaymentImport = BTaxPaymentImport(
            options["year"], options["month"]
        )
        b_tax_import.import_b_tax(self.stdout, verbosity=options["verbosity"])
