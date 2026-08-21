# SPDX-FileCopyrightText: 2026 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from suila.integrations.prisme.final_settlements import FinalSettlementExport
from suila.management.commands.common import SuilaBaseCommand


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        today = date.today()
        parser.add_argument(
            "--year",
            type=int,
            nargs="?",
            default=today.year - 1,
        )

    def _handle(self, *args, **options):
        export: FinalSettlementExport = FinalSettlementExport(options["year"])
        export.export_batches(self.stdout, verbosity=options["verbosity"])
