# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
from dataclasses import dataclass
from datetime import date
from typing import List

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from bf.models import (
    AIncomeReport,
    Employer,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)


def list_get(list, index):
    try:
        return list[index]
    except IndexError:
        return None


@dataclass
class IndkomstCSVFileLine:
    cpr: int
    arbejdsgiver: str
    cvr: int
    a_amounts: List[int]
    b_amounts: List[int]
    low: int
    high: int
    sum: int

    @classmethod
    def from_csv_row(cls, row):
        if len(row) > 3:
            return cls(
                cpr=int(list_get(row, 0)),
                arbejdsgiver=list_get(row, 1),
                cvr=int(list_get(row, 2)),
                a_amounts=cls._get_columns(row, 3, 3 + 12),
                b_amounts=cls._get_columns(row, 3 + 12, 3 + 24),
                low=list_get(row, 3 + 24),
                high=list_get(row, 3 + 24 + 1),
                sum=list_get(row, 3 + 24 + 2),
            )

    @staticmethod
    def _get_column(row, index: int, default: int = 0) -> int:
        try:
            return int(row[index]) or default
        except (ValueError, IndexError):
            return default

    @staticmethod
    def _get_columns(row, start: int, end: int) -> list[int]:
        return [
            IndkomstCSVFileLine._get_column(row, index) for index in range(start, end)
        ]

    @classmethod
    def validate_header_labels(cls, labels: List[str]):
        expected = (
            "CPR",
            "Arbejdsgiver navn",
            "Arbejdsgiver CVR",
            "Jan a-indkomst",
            "Feb a-indkomst",
            "Mar a-indkomst",
            "Apr a-indkomst",
            "Maj a-indkomst",
            "Jun a-indkomst",
            "Jul a-indkomst",
            "Aug a-indkomst",
            "Sep a-indkomst",
            "Okt a-indkomst",
            "Nov a-indkomst",
            "Dec a-indkomst",
            "Jan indh.-indkomst",
            "Feb indh.-indkomst",
            "Mar indh.-indkomst",
            "Apr indh.-indkomst",
            "Maj indh.-indkomst",
            "Jun indh.-indkomst",
            "Jul indh.-indkomst",
            "Aug indh.-indkomst",
            "Sep indh.-indkomst",
            "Okt indh.-indkomst",
            "Nov indh.-indkomst",
            "Dec indh.-indkomst",
            "Laveste indkomst beløb",
            "Højeste indkomst beløb",
            "A-indkomst for året",
        )
        for i, label in enumerate(expected):
            if i >= len(labels) or label != labels[i]:
                raise ValidationError(f"Expected '{label}' in header at position {i}")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file", type=str)
        parser.add_argument("--count", type=int)
        parser.add_argument("--year", type=int)
        parser.add_argument("--delimiter", type=str, default=";")
        parser.add_argument("--dry", action="store_true")

    def handle(self, *args, **kwargs):
        with open(kwargs["file"]) as input_stream:
            self._year = kwargs.get("year") or date.today().year
            self._delimiter = kwargs["delimiter"]
            dry = kwargs["dry"]
            rows = self._read_csv(input_stream, kwargs["count"])
            if dry:
                for row in rows:
                    print(row)
            else:
                self._create_or_update_objects(rows)

    def _read_csv(self, input_stream, count=None):
        reader = csv.reader(input_stream, delimiter=self._delimiter)

        IndkomstCSVFileLine.validate_header_labels(next(reader))

        for i, row in enumerate(reader):
            if count is not None and i >= count:
                break
            # We are not yet at last line in file. Parse it as a regular item
            line = IndkomstCSVFileLine.from_csv_row(row)
            if line:
                yield line

    @transaction.atomic
    def _create_or_update_objects(self, rows):
        rows = list(rows)

        # Create or update Year object
        year, _ = Year.objects.get_or_create(year=self._year)

        # Create or update Person objects
        persons = {
            cpr: Person(cpr=cpr, name=cpr) for cpr in set(row.cpr for row in rows)
        }
        Person.objects.bulk_create(
            persons.values(),
            update_conflicts=True,
            update_fields=("cpr",),
            unique_fields=("cpr",),
        )
        self.stdout.write(f"Processed {len(persons)} Person objects")

        # Create or update Employer objects
        employers = {cvr: Employer(cvr=cvr) for cvr in set(row.cvr for row in rows)}
        Employer.objects.bulk_create(
            employers.values(),
            update_conflicts=True,
            update_fields=("cvr",),
            unique_fields=("cvr",),
        )
        self.stdout.write(f"Processed {len(employers)} Employer objects")

        # Create or update PersonYear objects
        person_years = [
            PersonYear(person=person, year=year) for person in persons.values()
        ]
        PersonYear.objects.bulk_create(
            person_years,
            update_conflicts=True,
            update_fields=("person", "year"),
            unique_fields=("person", "year"),
        )
        self.stdout.write(f"Processed {len(person_years)} PersonYear objects")

        # Create or update PersonMonth objects
        person_months = {}
        for person_year in person_years:
            for month in range(1, 13):
                person_month = PersonMonth(
                    person_year=person_year,
                    month=month,
                    import_date=date.today(),
                )
                key = (person_year.person.cpr, month)
                person_months[key] = person_month
        PersonMonth.objects.bulk_create(
            person_months.values(),
            update_conflicts=True,
            update_fields=("import_date",),
            unique_fields=("person_year", "month"),
        )
        self.stdout.write(f"Processed {len(person_months)} PersonMonth objects")

        # Create AIncomeReport objects (existing objects for this year will be deleted!)
        a_income_reports = [
            AIncomeReport(
                person_month=person_months[(row.cpr, (index % 12) + 1)],
                employer=employers[row.cvr],
                amount=amount,
            )
            for row in rows
            for index, amount in enumerate(row.a_amounts)
            if amount != 0
        ]
        AIncomeReport.objects.filter(
            person_month__person_year__year=self._year
        ).delete()
        AIncomeReport.objects.bulk_create(a_income_reports)
        self.stdout.write(f"Created {len(a_income_reports)} AIncomeReport objects")

        # Create MonthlyBIncomeReport objects (existing objects for this year will be deleted!)
        b_income_reports = [
            MonthlyBIncomeReport(
                person_month=person_months[(row.cpr, (index % 12) + 1)],
                trader=employers[row.cvr],
                amount=amount,
            )
            for row in rows
            for index, amount in enumerate(row.b_amounts)
            if amount != 0
        ]
        MonthlyBIncomeReport.objects.filter(
            person_month__person_year__year=self._year
        ).delete()
        MonthlyBIncomeReport.objects.bulk_create(b_income_reports)
        self.stdout.write(
            f"Created {len(b_income_reports)} MonthlyBIncomeReport objects"
        )
