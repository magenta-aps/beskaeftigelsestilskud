# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import re
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import QuerySet

from suila.integrations.prisme.csv_format import CSVFormat
from suila.integrations.prisme.sftp_import import SFTPImport
from suila.models import PrismeBatchItem

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

    def import_posting_status(self, stdout: OutputWrapper, verbosity: int):
        new_filenames: list[str] = self._process_filenames(self.get_new_filenames())
        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            self._update_prisme_batch_items(filename)

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

    def _process_filenames(self, filenames: set[str]) -> list[str]:
        # Perform any filtering or sorting of incoming filenames here
        def sort_by_filename_date(item: tuple[str, re.Match]) -> tuple[int, ...]:
            """Return a tuple of integer values for the year, month, day and time
            present in `filename`"""
            # This allows sorting the incoming filenames chronologically
            filename: str
            match: re.Match
            filename, match = item
            return tuple(
                [int(match.group(name)) for name in ("year", "month", "day", "time")]
            )

        # Construct pattern matching the filenames we are interested in
        machine_id: str = settings.PRISME["machine_id"]
        pattern: re.Pattern = re.compile(
            rf"§38_{machine_id:05d}_"
            r"(?P<day>\d{2})-"
            r"(?P<month>\d{2})-"
            r"(?P<year>\d{4})_"
            r"(?P<time>\d{6})\.csv"
        )

        # Keep only the filenames that match `pattern`
        matches: list[tuple[str, re.Match]] = [
            (filename, pattern.match(filename))
            for filename in filenames
            if pattern.match(filename)
        ]

        # Return the filenames in the order by specified by `sort_by_filename_date`
        return [
            filename for filename, match in sorted(matches, key=sort_by_filename_date)
        ]

    def _parse(self, filename: str) -> list[PostingStatus]:
        return PostingStatus.from_csv_buf(self.get_file(filename))

    def _get_prisme_batch_items(self) -> QuerySet[PrismeBatchItem]:
        return PrismeBatchItem.objects.select_related(
            "person_month__person_year__person",
            "person_month__person_year__year",
        )

    @transaction.atomic
    def _update_prisme_batch_items(self, filename: str):
        qs: QuerySet[PrismeBatchItem] = self._get_prisme_batch_items()
        print(f"Processing {qs.count()} Prisme batch items ...")

        rows: list[PostingStatus] = self._parse(filename)
        matches: list[PrismeBatchItem] = []
        for row in rows:
            try:
                item: PrismeBatchItem = qs.get(invoice_no=row.invoice_no)
            except PrismeBatchItem.DoesNotExist:
                logger.debug(
                    "No Prisme batch item found for invoice number %s",
                    row.invoice_no,
                )
            else:
                item.status = PrismeBatchItem.PostingStatus.Failed
                item.posting_status_filename = filename
                item.error_code = row.error_code
                item.error_description = row.error_description
                matches.append(item)

        num_failed: int = qs.bulk_update(
            matches,
            ["status", "posting_status_filename", "error_code", "error_description"],
        )
        print(f"Updated {num_failed} to status=failed")

        # qs = self._get_prisme_batch_items()
        num_succeeded: int = qs.exclude(
            status=PrismeBatchItem.PostingStatus.Failed
        ).update(
            status=PrismeBatchItem.PostingStatus.Posted,
            posting_status_filename=filename,
            error_code="",
            error_description="",
        )
        print(f"Updated {num_succeeded} to status=posted")
        print()


class PostingStatusImportMissingInvoiceNumber(SFTPImport):
    """Import posting status for lines where we cannot match the invoice number to
    `PrismeBatchItem.invoice_no`. Tries to match on CPR, date and amount instead.
    """

    @transaction.atomic
    def import_posting_status(self, stdout: OutputWrapper, verbosity: int):
        filenames: set[str] = self.get_new_filenames()
        items: list[PrismeBatchItem] = []
        qs: QuerySet[PrismeBatchItem] = PrismeBatchItem.objects.select_related(
            "person_month__person_year__person",
            "person_month__person_year__year",
        )

        for filename in filenames:
            stdout.write(f"Loading file: {filename}\n")
            rows: list[PostingStatus] = PostingStatus.from_csv_buf(
                self.get_file(filename)
            )
            for row in rows:
                issue_date = row.due_date - relativedelta(months=2, day=1)
                try:
                    item: PrismeBatchItem = qs.get(
                        person_month__person_year__person__cpr=f"{row.cpr:010d}",
                        person_month__person_year__year__year=issue_date.year,
                        person_month__month=issue_date.month,
                        person_month__benefit_paid=row.amount,
                    )
                except PrismeBatchItem.DoesNotExist:
                    logger.info(
                        "No Prisme batch item found for "
                        "cpr %r, issue date %r, amount %r",
                        row.cpr,
                        issue_date,
                        row.amount,
                    )
                else:
                    # Mark Prisme batch item as failed
                    item.status = PrismeBatchItem.PostingStatus.Failed
                    item.posting_status_filename = filename
                    item.error_code = row.error_code
                    item.error_description = row.error_description
                    items.append(item)

        PrismeBatchItem.objects.bulk_update(
            items,
            ["status", "posting_status_filename", "error_code", "error_description"],
        )
        stdout.write(f"Updated posting status for {len(items)} Prisme batch items")
        return items

    def get_remote_folder_name(self) -> str:
        return settings.PRISME["posting_status_folder"]  # type: ignore[misc]

    def get_known_filenames(self) -> set[str]:
        return set()  # always empty set
