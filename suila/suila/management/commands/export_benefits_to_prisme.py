# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from suila.integrations.prisme.benefits import BatchExport
from suila.management.commands.common import SuilaBaseCommand


class Command(SuilaBaseCommand):
    filename = __file__

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
        super().add_arguments(parser)

    def _handle(self, *args, **options):

        # Always export for two months back
        year = options["year"]
        month = options["month"]
        month -= 2
        if month < 1:
            month += 12
            year -= 1

        batch_export: BatchExport = BatchExport(year, month)
        batch_export.export_batches(self.stdout, verbosity=options["verbosity"])
