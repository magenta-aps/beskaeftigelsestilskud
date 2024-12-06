# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from bf.integrations.prisme.benefits import BatchExport
from bf.management.commands.common import BfBaseCommand


class Command(BfBaseCommand):
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
        batch_export: BatchExport = BatchExport(options["year"], options["month"])
        batch_export.export_batches(self.stdout, verbosity=options["verbosity"])
