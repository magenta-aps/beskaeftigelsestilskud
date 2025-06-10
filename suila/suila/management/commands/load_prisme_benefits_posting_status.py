# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from suila.integrations.prisme.posting_status import PostingStatusImport
from suila.management.commands.common import SuilaBaseCommand


class Command(SuilaBaseCommand):
    filename = __file__

    def _handle(self, *args, **options):
        posting_status_import: PostingStatusImport = PostingStatusImport()
        posting_status_import.import_posting_status(
            self.stdout, verbosity=options["verbosity"]
        )
