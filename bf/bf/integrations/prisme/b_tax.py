# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date

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

    def __init__(self, year: int, month: int):
        self._year = year
        self._month = month

    @transaction.atomic()
    def import_b_tax(self, stdout: OutputWrapper, verbosity: int):
        known_filenames: set[str] = self._get_known_filenames()
        new_filenames: set[str] = self.get_new_filenames(known_filenames)

        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            rows: list[BTaxPayment] = self._parse(filename)
            self._create_objects(filename, rows)
            if verbosity >= 2:
                for row in rows:
                    stdout.write(f"{row}\n")
                stdout.write("\n")

        stdout.write("All done\n")

    def get_remote_folder_name(self) -> str:
        prisme: dict = settings.PRISME
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

    def _create_objects(
        self,
        filename: str,
        rows: list[BTaxPayment],
    ) -> list[BTaxPaymentModel]:
        objs: list[BTaxPaymentModel] = [
            BTaxPaymentModel(
                filename=filename,
                person_month=self._get_person_month(row),
                amount_paid=row.amount_paid,
                amount_charged=row.amount_charged,
                date_charged=row.date_charged,
                rate_number=row.rate_number,
                serial_number=row.serial_number,
            )
            for row in rows
        ]
        return BTaxPaymentModel.objects.bulk_create(objs)

    def _get_person_month(self, row: BTaxPayment) -> PersonMonth:
        return PersonMonth.objects.get(
            person_year__person__cpr=row.cpr,
            person_year__year__year=row.tax_year,
            month=row.rate_number,
        )
