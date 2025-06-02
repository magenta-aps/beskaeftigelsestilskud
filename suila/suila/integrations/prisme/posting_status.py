# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import re
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import DateField, F, Func, Q, QuerySet, Value

from suila.integrations.prisme.csv_format import CSVFormat
from suila.integrations.prisme.sftp_import import SFTPImport
from suila.models import PrismeBatchItem, PrismePostingStatusFile

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

    def import_posting_status(self, stdout: OutputWrapper, verbosity: int):
        new_filenames: list[str] = self._process_filenames(self.get_new_filenames())
        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}")
            self._update_prisme_batch_items(filename, stdout)

    def get_remote_folder_name(self) -> str:
        return settings.PRISME["posting_status_folder"]  # type: ignore[misc]

    def get_known_filenames(self) -> set[str]:
        known_filenames: set[str] = set(
            PrismePostingStatusFile.objects.values_list("filename", flat=True)
        )
        return known_filenames

    def _process_filenames(self, filenames: set[str]) -> list[str]:
        # Perform any filtering or sorting of incoming filenames here

        def sort_by_filename_date(item: tuple[str, re.Match]) -> tuple[int, ...]:
            """Return a tuple of integer values for the year, month, day and time
            present in `filename`"""
            # This allows sorting the incoming filenames chronologically
            filename: str
            match: re.Match | None
            filename, match = item
            return tuple(
                [int(match.group(name)) for name in ("year", "month", "day", "time")]
            )

        # Construct pattern matching the filenames we are interested in
        machine_id: str = settings.PRISME["machine_id"]  # type: ignore[misc]
        pattern: re.Pattern = re.compile(
            rf"§38_{machine_id:05d}_"
            r"(?P<day>\d{2})-"
            r"(?P<month>\d{2})-"
            r"(?P<year>\d{4})_"
            r"(?P<time>\d{6})\.csv"
        )

        # Keep only the filenames that match `pattern`
        matches: list[tuple[str, re.Match | None]] = [
            (filename, pattern.match(filename))
            for filename in filenames
            if pattern.match(filename)
        ]

        # Return the filenames in the order by specified by `sort_by_filename_date`
        return [
            filename
            for filename, match in sorted(
                matches, key=sort_by_filename_date  # type: ignore
            )
        ]

    def _parse(self, filename: str) -> list[PostingStatus]:
        return PostingStatus.from_csv_buf(self.get_file(filename))

    def _get_prisme_batch_items(self) -> QuerySet[PrismeBatchItem]:
        return PrismeBatchItem.objects.select_related(
            "person_month__person_year__person",
            "person_month__person_year__year",
        )

    def _get_max_date(self, rows: list[PostingStatus]) -> date:
        max_date: date = max(
            row.due_date - relativedelta(months=2, day=1) for row in rows
        )
        return max_date

    def _filter_prisme_batch_items_on_date(
        self,
        qs: QuerySet[PrismeBatchItem],
        max_date: date,
    ) -> QuerySet[PrismeBatchItem]:
        # Filter the queryset based on the latest date encountered in the input file.
        # We should not update any Prisme batch items whose person month occurs later
        # than the latest due date in the file, minus two months.
        qs = qs.annotate(
            # Add column `_date` containing a `DateField` value built from the year
            # and month of each person month in the queryset.
            _date=Func(
                F("person_month__person_year__year__year"),
                F("person_month__month"),
                Value(1),  # 1st of the month
                function="make_date",
                output_field=DateField(),
            )
        )
        return qs.filter(_date__lte=max_date)

    @transaction.atomic
    def _update_prisme_batch_items(self, filename: str, stdout: OutputWrapper):
        rows: list[PostingStatus] = self._parse(filename)
        max_date: date = self._get_max_date(rows)
        qs: QuerySet[PrismeBatchItem] = self._get_prisme_batch_items()
        qs = self._filter_prisme_batch_items_on_date(qs, max_date)

        stdout.write(
            f"Processing {qs.count()} Prisme batch items (max date = {max_date}) ..."
        )

        # Register this file as imported
        posting_status_file, _ = PrismePostingStatusFile.objects.get_or_create(
            filename=filename
        )

        # The items whose invoice number match a line in the file change status to
        # `Failed`.
        matches: list[PrismeBatchItem] = []
        for row in rows:
            try:
                item: PrismeBatchItem = qs.get(invoice_no=row.invoice_no)
            except PrismeBatchItem.DoesNotExist:
                logger.debug(
                    "No Prisme batch item found for invoice number %s",
                    row.invoice_no,
                )
                # Try to look up by CPR/date/amount instead
                issue_date = row.due_date - relativedelta(months=2, day=1)
                try:
                    item = qs.get(
                        person_month__person_year__person__cpr=f"{row.cpr:010d}",
                        person_month__person_year__year__year=issue_date.year,
                        person_month__month=issue_date.month,
                        person_month__benefit_transferred=row.amount,
                    )
                except PrismeBatchItem.DoesNotExist:
                    logger.debug(
                        "No Prisme batch item found for CPR %s, year %r, month %r, "
                        "amount %r",
                        f"{row.cpr:010d}",
                        issue_date.year,
                        issue_date.month,
                        row.amount,
                    )
                    # Go to next row in CSV
                    continue

            item.status = PrismeBatchItem.PostingStatus.Failed
            item.posting_status_file = posting_status_file
            item.error_code = row.error_code
            item.error_description = row.error_description
            matches.append(item)

        num_failed: int = qs.bulk_update(
            matches,
            ["status", "posting_status_file", "error_code", "error_description"],
        )
        stdout.write(f"Updated {num_failed} to status=failed")

        # The remaining items change status to `Posted`.
        # Any previous `error_code` or `error_description` is cleared.
        num_succeeded: int = qs.exclude(
            Q(pk__in=[item.pk for item in matches])
            | Q(status=PrismeBatchItem.PostingStatus.Posted)
        ).update(
            status=PrismeBatchItem.PostingStatus.Posted,
            posting_status_file=posting_status_file,
            error_code="",
            error_description="",
        )
        stdout.write(f"Updated {num_succeeded} to status=posted")
        stdout.write("\n")
