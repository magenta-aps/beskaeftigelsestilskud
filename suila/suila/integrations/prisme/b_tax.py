# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date
from functools import cache
from itertools import groupby

from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management.base import OutputWrapper
from django.db import transaction

from suila.integrations.prisme.csv_format import CSVFormat
from suila.integrations.prisme.sftp_import import SFTPImport
from suila.models import BTaxPayment as BTaxPaymentModel
from suila.models import DataLoad, Person, PersonMonth, PersonYear, Year


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


@dataclass(frozen=True)
class BTaxPaymentImportResult:
    """Represents the result of running a B tax import"""

    objs: list[BTaxPaymentModel]
    matched: list[BTaxPayment]
    unmatched: list[BTaxPayment]


class BTaxPaymentImport(SFTPImport):
    """Import one or more B tax CSV files from Prisme SFTP"""

    @transaction.atomic()
    def import_b_tax(
        self,
        stdout: OutputWrapper,
        verbosity: int,
    ) -> BTaxPaymentImportResult:
        new_filenames: set[str] = self.get_new_filenames()

        all_objs: list[BTaxPaymentModel] = []
        all_matched: list[BTaxPayment] = []
        all_unmatched: list[BTaxPayment] = []

        for filename in new_filenames:
            stdout.write(f"Loading new file: {filename}\n")
            # Split rows in CSV into `matched` and `unmatched` rows
            rows: list[BTaxPayment] = self._parse(filename)
            matched, unmatched = self._split_rows(rows)
            # Add to lists
            all_matched.extend(matched)
            all_unmatched.extend(unmatched)
            # Create objects for matched rows
            objs: list[BTaxPaymentModel] = self._create_objects(
                filename, matched, unmatched
            )
            all_objs.extend(objs)
            # List processed data
            if verbosity >= 2:
                for obj in objs:
                    stdout.write(f"Created {obj}\n")

        stdout.write("All done\n")

        return BTaxPaymentImportResult(
            objs=all_objs, matched=all_matched, unmatched=all_unmatched
        )

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

    def _parse(self, filename: str) -> list[BTaxPayment]:
        return BTaxPayment.from_csv_buf(self.get_file(filename))

    @cache
    def _get_person_month(
        self, cpr: str, tax_year: int, rate_number: int
    ) -> PersonMonth | None:
        qs = PersonMonth.objects.select_related(
            "person_year__person", "person_year__year"
        )
        try:
            return qs.get(
                person_year__person__cpr=cpr,
                person_year__year__year=tax_year,
                month=rate_number,
            )
        except PersonMonth.DoesNotExist:
            return None

    def _split_rows(
        self, rows: list[BTaxPayment]
    ) -> tuple[list[BTaxPayment], list[BTaxPayment]]:
        def key(row: BTaxPayment) -> bool:
            return (
                self._get_person_month(row.cpr, row.tax_year, row.rate_number)
                is not None
            )

        # Split rows by whether they have a matching `PersonMonth`, or not
        split: dict[bool, list[BTaxPayment]] = {
            k: list(v) for k, v in groupby(sorted(rows, key=key), key=key)
        }

        # Return tuple of matched and unmatched rows, respectively
        return split.get(True, []), split.get(False, [])

    def _create_objects(
        self,
        filename: str,
        matched: list[BTaxPayment],
        unmatched: list[BTaxPayment],
    ) -> list[BTaxPaymentModel]:
        result: list[BTaxPaymentModel] = []
        objs: list[BTaxPaymentModel]

        # Create `BTaxPayment` objects for input rows in `matched`
        objs = [
            BTaxPaymentModel(
                filename=filename,
                person_month=self._get_person_month(
                    match.cpr, match.tax_year, match.rate_number
                ),
                amount_paid=abs(match.amount_paid),  # input value is always negative
                amount_charged=match.amount_charged,
                date_charged=match.date_charged,
                rate_number=match.rate_number,
                serial_number=match.serial_number,
            )
            for match in matched
        ]
        result.extend(BTaxPaymentModel.objects.bulk_create(objs))

        if len(unmatched) > 0:
            # Create `PersonMonth` objects for input rows in `unmatched`
            unmatched_person_months = self._create_person_months_for_unmatched(
                unmatched
            )
            # Create `BTaxPayment` objects for input rows in `unmatched`
            objs = [
                BTaxPaymentModel(
                    filename=filename,
                    person_month=person_month,
                    amount_paid=abs(unmatch.amount_paid),  # input value always negative
                    amount_charged=unmatch.amount_charged,
                    date_charged=unmatch.date_charged,
                    rate_number=unmatch.rate_number,
                    serial_number=unmatch.serial_number,
                )
                for unmatch, person_month in unmatched_person_months
            ]
            result.extend(BTaxPaymentModel.objects.bulk_create(objs))

        return result

    def _create_person_months_for_unmatched(
        self,
        unmatched: list[BTaxPayment],
    ) -> list[tuple[BTaxPayment, PersonMonth | None]]:
        if len(unmatched) == 0:
            return []

        result: list[tuple[BTaxPayment, PersonMonth | None]] = []
        load = DataLoad.objects.create(source="btax")

        for unmatch in unmatched:
            # Only create `PersonMonth`, etc. if `BTaxPayment` indicates an actual
            # rate payment.
            if abs(unmatch.amount_paid) > 0:
                year, _ = Year.objects.get_or_create(year=unmatch.tax_year)
                person, _ = Person.objects.get_or_create(
                    cpr=unmatch.cpr,
                    defaults={"load": load},
                )
                person_year, _ = PersonYear.objects.get_or_create(
                    year=year,
                    person=person,
                    defaults={"load": load},
                )
                person_month = PersonMonth.objects.create(
                    load=load,
                    person_year=person_year,
                    import_date=date.today(),
                    month=unmatch.rate_number,
                )
                result.append((unmatch, person_month))
            else:
                result.append((unmatch, None))

        return result
