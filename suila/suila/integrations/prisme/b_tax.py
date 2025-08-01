# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import logging
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management.base import OutputWrapper
from django.db import transaction
from tenQ.client import ClientException

from suila.exceptions import BTaxFilesNotFound
from suila.integrations.prisme.csv_format import CSVFormat
from suila.integrations.prisme.sftp_import import SFTPImport
from suila.models import BTaxPayment as BTaxPaymentModel
from suila.models import DataLoad, Person, PersonMonth, PersonYear, Year

logger = logging.getLogger(__name__)


def get_b_tax_file_timestamp(filename: str) -> datetime.datetime:
    """
    Returns the timestamp of a btax-file. Example btax filenames are:
        - BSKAT_2022_207022_27-01-2025_120035.csv
        - BSKAT_2025_207025_04-04-2025_123221.csv
        - BSKAT_2025_207025_04-04-2025_150240.csv
        - BSKAT_2025_207025_04-06-2025_084620.csv
        - BSKAT_2025_207025_04-06-2025_085736.csv
        - BSKAT_2025_207025_04-06-2025_085947.csv
        - BSKAT_2025_207025_04-07-2025_070613.csv
        - BSKAT_2025_207025_04-07-2025_071049.csv
        - BSKAT_2025_207025_04-07-2025_071421.csv
        - BSKAT_2025_207025_04-07-2025_071604.csv
        - BSKAT_2025_207025_04-07-2025_072506.csv
        - BSKAT_2025_207025_05-06-2025_100100.csv
        - BSKAT_2025_207025_09-05-2025_082451.csv
        - BSKAT_2025_207025_09-05-2025_082854.csv
        - BSKAT_2025_207025_09-05-2025_093200.csv
    """
    return datetime.datetime.strptime(filename.split("_")[3], "%d-%m-%Y")


@dataclass(frozen=True)
class BTaxPayment(CSVFormat):
    """Represents a single line in a "B tax payment" CSV file"""

    type: str
    cpr: str
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
            cpr=row[1],
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

    @transaction.atomic()
    def import_b_tax(
        self,
        year: int,
        month: int,
        stdout: OutputWrapper,
        verbosity: int,
        force=False,
    ) -> list[BTaxPaymentModel]:
        new_filenames: list[str] = [
            f
            for f in self.get_new_filenames()
            if (f.endswith(".csv") and f.startswith("BSKAT"))
        ]
        all_objs: list[BTaxPaymentModel] = []

        if not new_filenames:
            raise BTaxFilesNotFound()

        # Check if there are files which match the year/month we are in.
        relevant_file_found = any(
            (file_date := get_b_tax_file_timestamp(filename)).month == month
            and file_date.year == year
            for filename in new_filenames
        )

        if not relevant_file_found and not force:
            raise BTaxFilesNotFound(month=month)

        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            rows: list[BTaxPayment] | None = self._parse(filename)
            if rows is not None:
                objs: list[BTaxPaymentModel] = self._create_objects(filename, rows)
                all_objs.extend(objs)
                # List processed data
                if verbosity >= 2:
                    for obj in objs:
                        stdout.write(f"Created {obj}\n")
            else:
                stdout.write(
                    f"Failed to load new file {filename}\n"
                )  # pragma: no cover

        stdout.write("All done\n")

        return all_objs

    def get_remote_folder_name(self) -> str:
        return settings.PRISME["b_tax_folder"]  # type: ignore[misc]

    def get_known_filenames(self) -> set[str]:
        known_filenames: set[str] = set(
            BTaxPaymentModel.objects.aggregate(
                filenames=ArrayAgg("filename", distinct=True)
            )["filenames"]
            or set()
        )
        return known_filenames

    def _parse(self, filename: str) -> list[BTaxPayment] | None:
        try:
            buf: BytesIO = self.get_file(filename)
        except ClientException:
            logger.exception("encountered error when retrieving file %r", filename)
            return None
        else:
            return BTaxPayment.from_csv_buf(buf)

    def _create_objects(
        self,
        filename: str,
        rows: list[BTaxPayment],
    ) -> list[BTaxPaymentModel]:
        person_months: list[tuple[BTaxPayment, PersonMonth | None]] = []
        load = DataLoad.objects.create(source="btax")

        for row in rows:
            # Only create `PersonMonth`, etc. if `BTaxPayment` indicates an actual
            # rate payment.
            if abs(row.amount_paid) > 0:
                year, _ = Year.objects.get_or_create(year=row.tax_year)
                person, _ = Person.objects.get_or_create(
                    cpr=row.cpr,
                    defaults={"load": load},
                )
                person_year, _ = PersonYear.objects.get_or_create(
                    year=year,
                    person=person,
                    defaults={"load": load},
                )
                # Find existing `PersonMonth`, or create a new `PersonMonth` if not
                try:
                    person_month = PersonMonth.objects.get(
                        person_year=person_year,
                        month=row.rate_number,
                    )
                except PersonMonth.DoesNotExist:
                    person_month = PersonMonth.objects.create(
                        load=load,
                        person_year=person_year,
                        import_date=date.today(),
                        month=row.rate_number,
                    )
                person_months.append((row, person_month))
            else:
                person_months.append((row, None))

        # Update `PersonMonth.has_paid_b_tax` for all person months that were found or
        # created.
        person_month_list = [
            person_month for row, person_month in person_months if person_month
        ]
        for person_month in person_month_list:
            person_month.has_paid_b_tax = True
        PersonMonth.objects.bulk_update(
            person_month_list,
            ["has_paid_b_tax"],
            batch_size=1000,
        )

        # Create `BTaxPayment` objects for input rows in `person_months`
        objs: list[BTaxPaymentModel] = [
            BTaxPaymentModel(
                filename=filename,
                person_month=person_month,
                cpr=row.cpr,
                amount_paid=abs(row.amount_paid),  # input value is always negative
                amount_charged=row.amount_charged,
                date_charged=row.date_charged,
                rate_number=row.rate_number,
                serial_number=row.serial_number,
            )
            for row, person_month in person_months
        ]
        BTaxPaymentModel.objects.bulk_create(
            objs,
            update_conflicts=True,
            update_fields=(
                "filename",
                "person_month",
                "amount_paid",
                "amount_charged",
                "date_charged",
                "rate_number",
                "serial_number",
            ),
            unique_fields=(
                "cpr",
                "amount_paid",
                "amount_charged",
                "date_charged",
                "rate_number",
            ),
            batch_size=1000,
        )

        return objs
