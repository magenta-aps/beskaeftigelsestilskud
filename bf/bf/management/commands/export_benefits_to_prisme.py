# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from django.core.management.base import BaseCommand

from bf.exports.prisme.benefits import BatchExport


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
        batch_export: BatchExport = BatchExport(options["year"], options["month"])
        batch_export.export_batches(self.stdout)
