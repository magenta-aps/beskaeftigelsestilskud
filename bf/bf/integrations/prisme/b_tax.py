# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date
from itertools import groupby

from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management.base import OutputWrapper
from django.db import transaction

from bf.integrations.prisme.csv_format import CSVFormat
from bf.integrations.prisme.sftp_import import SFTPImport
from bf.models import BTaxPayment as BTaxPaymentModel
from bf.models import PersonMonth


@dataclass(frozen=True)
class BTaxPayment(CSVFormat):
    """Represents a single line in a "B tax payment" CSV file"""

    type: str
    cpr: int
    tax_year: int
    amount_paid: int
    serial_number: int
    amount_charged: int
    date_charged: date
    rate_number: int

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "BTaxPayment":
        return cls(
            type=row[0],
            cpr=int(row[1]),
            # row[2] is always empty
            tax_year=int(row[3]),
            amount_paid=int(row[4]),
            serial_number=int(row[5]),
            amount_charged=int(row[6]),
            date_charged=cls.parse_date(row[7]),
            rate_number=int(row[8]),
        )


class BTaxPaymentImport(SFTPImport):
    """Import one or more B tax CSV files from Prisme SFTP"""

    def __init__(self):
        super().__init__()
        # Construct dictionary which maps `(cpr, year, month)` tuples to `PersonMonth`
        # objects.
        self._person_months_keyed: dict[tuple[int, int, int], PersonMonth] = {
            (int(pm.person_year.person.cpr), pm.person_year.year.year, pm.month): pm
            for pm in PersonMonth.objects.select_related(
                "person_year__person", "person_year__year"
            )
        }

    @transaction.atomic()
    def import_b_tax(
        self, stdout: OutputWrapper, verbosity: int
    ) -> tuple[list[BTaxPaymentModel], list[BTaxPayment]]:
        created: list[BTaxPaymentModel] = []
        skipped: list[BTaxPayment] = []

        known_filenames: set[str] = self._get_known_filenames()
        new_filenames: set[str] = self.get_new_filenames(known_filenames)

        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            # Split rows in CSV into `matched` and `unmatched` rows
            all_rows: list[BTaxPayment] = self._parse(filename)
            matched: list[BTaxPayment]
            unmatched: list[BTaxPayment]
            matched, unmatched = self._split_rows(all_rows)
            # Create objects for matched rows
            objs: list[BTaxPaymentModel] = self._create_objects(filename, matched)
            # Update lists of created objects and skipped input rows
            created.extend(objs)
            skipped.extend(unmatched)
            # List processed data
            if verbosity >= 2:
                for obj in created:
                    stdout.write(f"Created {obj}\n")
                for row in unmatched:
                    stdout.write(
                        f"Could not import {row} (no matching `PersonMonth`)\n"
                    )
                stdout.write("\n")

        stdout.write("All done\n")

        return created, skipped

    def get_remote_folder_name(self) -> str:
        prisme: dict = settings.PRISME  # type: ignore[misc]
        remote_folder: str = prisme["b_tax_folder"]
        return remote_folder

    def _get_known_filenames(self) -> set[str]:
        known_filenames: set[str] = set(
            BTaxPaymentModel.objects.aggregate(
                filenames=ArrayAgg("filename", distinct=True)
            )["filenames"]
            or set()
        )
        return known_filenames

    def _parse(self, filename: str) -> list[BTaxPayment]:
        return BTaxPayment.from_csv_buf(self.get_file(filename))

    def _split_rows(
        self, rows: list[BTaxPayment]
    ) -> tuple[list[BTaxPayment], list[BTaxPayment]]:
        def key(row: BTaxPayment) -> bool:
            return (row.cpr, row.tax_year, row.rate_number) in self._person_months_keyed

        # Split rows by whether they have a matching `PersonMonth`, or not
        split: dict[bool, list[BTaxPayment]] = {
            k: list(v) for k, v in groupby(sorted(rows, key=key), key=key)
        }

        # Return tuple of matched and unmatched rows, respectively
        return split.get(True, []), split.get(False, [])

    def _create_objects(
        self,
        filename: str,
        rows: list[BTaxPayment],
    ) -> list[BTaxPaymentModel]:
        # Construct list of objects to insert
        objs: list[BTaxPaymentModel] = [
            BTaxPaymentModel(
                filename=filename,
                person_month=self._person_months_keyed[
                    (row.cpr, row.tax_year, row.rate_number)
                ],
                amount_paid=abs(row.amount_paid),  # input value is always negative
                amount_charged=row.amount_charged,
                date_charged=row.date_charged,
                rate_number=row.rate_number,
                serial_number=row.serial_number,
            )
            for row in rows
        ]
        return BTaxPaymentModel.objects.bulk_create(objs)
