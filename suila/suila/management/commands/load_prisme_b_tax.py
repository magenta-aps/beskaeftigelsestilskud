# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from suila.integrations.prisme.b_tax import BTaxPaymentImport
from suila.management.commands.common import SuilaBaseCommand


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)
        parser.add_argument("--force", type=bool, default=False)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        b_tax_import: BTaxPaymentImport = BTaxPaymentImport()
        b_tax_import.import_b_tax(
            kwargs["year"],
            kwargs["month"],
            self.stdout,
            kwargs.get("verbosity", 0),
            force=kwargs["force"],
        )
