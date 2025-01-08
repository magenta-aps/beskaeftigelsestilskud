# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import QuerySet

from suila.integrations.prisme.csv_format import CSVFormat
from suila.integrations.prisme.sftp_import import SFTPImport
from suila.models import PrismeBatch, PrismeBatchItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostingStatus(CSVFormat):
    """Represents a single line in a "posting status" CSV file"""

    type: str
    cpr: int
    invoice_no: str
    amount: int
    due_date: date
    error_code: str
    error_description: str
    voucher_no: str

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "PostingStatus":
        return cls(
            type=row[0],
            cpr=int(row[1]),
            invoice_no=row[2],
            amount=int(row[3]),
            due_date=cls.parse_date(row[4]),
            error_code=row[5],
            error_description=row[6],
            voucher_no=row[7],
        )


class PostingStatusImport(SFTPImport):
    """Import one or more posting status CSV files from Prisme SFTP"""

    def __init__(self, year: int, month: int):
        super().__init__()
        self._year = year
        self._month = month

    @transaction.atomic()
    def import_posting_status(self, stdout: OutputWrapper, verbosity: int):
        new_filenames: set[str] = self.get_new_filenames()

        # Process new files, marking relevant items as "failed to post"
        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            rows: list[PostingStatus] = self._parse(filename)
            self._update_failed_items(filename, rows)
            if verbosity >= 2:
                for row in rows:
                    stdout.write(f"{row}\n")
                stdout.write("\n")

        # Always mark all other items in relevant time period as succeeded
        succeeded: int = self._update_succeeded_items()
        stdout.write(f"Marked {succeeded} Prisme batch items as successfully posted\n")

    def get_remote_folder_name(self) -> str:
        return settings.PRISME["posting_status_folder"]  # type: ignore[misc]

    def get_known_filenames(self) -> set[str]:
        known_filenames: set[str] = set(
            PrismeBatchItem.objects.aggregate(
                filenames=ArrayAgg("posting_status_filename", distinct=True)
            )["filenames"]
            or set()
        )
        return known_filenames

    def _parse(self, filename: str) -> list[PostingStatus]:
        return PostingStatus.from_csv_buf(self.get_file(filename))

    def _update_failed_items(self, filename: str, rows: list[PostingStatus]):
        items: list[PrismeBatchItem] = []
        for row in rows:
            try:
                item: PrismeBatchItem = PrismeBatchItem.objects.get(
                    invoice_no=row.invoice_no
                )
            except PrismeBatchItem.DoesNotExist:
                logger.info(
                    "No Prisme batch item found for invoice number %s",
                    row.invoice_no,
                )
            else:
                item.status = PrismeBatchItem.PostingStatus.Failed
                item.posting_status_filename = filename
                item.error_code = row.error_code
                item.error_description = row.error_description
                items.append(item)

        PrismeBatchItem.objects.bulk_update(
            items,
            ["status", "posting_status_filename", "error_code", "error_description"],
        )

        return items

    def _update_succeeded_items(self) -> int:
        assert date(self._year, self._month, 1) < date.today()
        qs: QuerySet[PrismeBatchItem] = PrismeBatchItem.objects.filter(
            status=PrismeBatchItem.PostingStatus.Sent,
            prisme_batch__status=PrismeBatch.Status.Sent,
            person_month__person_year__year__year__lte=self._year,
            person_month__month__lte=self._month,
        )
        return qs.update(status=PrismeBatchItem.PostingStatus.Posted)
