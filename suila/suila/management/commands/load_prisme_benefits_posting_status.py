# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from django.core.management.base import BaseCommand

from suila.integrations.prisme.posting_status import PostingStatusImport


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
        posting_status_import: PostingStatusImport = PostingStatusImport(
            options["year"], options["month"]
        )
        posting_status_import.import_posting_status(
            self.stdout, verbosity=options["verbosity"]
        )
