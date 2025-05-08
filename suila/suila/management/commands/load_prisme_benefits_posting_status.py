# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.core.management.base import BaseCommand

from suila.integrations.prisme.posting_status import (
    PostingStatusImport,
    PostingStatusImportMissingInvoiceNumber,
)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--unknown-invoice-number",
            action="store_true",
            help="Process posting status for unknown invoice numbers",
        )

    def handle(self, *args, **options):
        if options["unknown_invoice_number"]:
            posting_status_import: PostingStatusImportMissingInvoiceNumber = (
                PostingStatusImportMissingInvoiceNumber()
            )
        else:
            posting_status_import: PostingStatusImport = PostingStatusImport()

        posting_status_import.import_posting_status(
            self.stdout, verbosity=options["verbosity"]
        )
