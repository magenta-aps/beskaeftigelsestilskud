# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.core.management.base import BaseCommand

from suila.integrations.prisme.b_tax import BTaxPaymentImport


class Command(BaseCommand):
    def handle(self, *args, **options):
        b_tax_import: BTaxPaymentImport = BTaxPaymentImport()
        b_tax_import.import_b_tax(self.stdout, verbosity=options["verbosity"])
