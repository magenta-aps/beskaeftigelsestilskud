# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
from dataclasses import dataclass
from datetime import date
from typing import List

from django.core.management.base import BaseCommand
from django.db import transaction

from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear, Year


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
    amounts: List[int]

    @classmethod
    def from_csv_row(cls, row):
        if len(row) > 3:
            return cls(
                cpr=int(list_get(row, 0)),
                arbejdsgiver=list_get(row, 1),
                cvr=int(list_get(row, 2)),
                amounts=cls._get_columns(row, 3, 3 + 24),
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

        next(reader)  # skip csv header

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

        # Create ASalaryReport objects (existing objects for this year will be deleted!)
        a_salary_reports = [
            ASalaryReport(
                person_month=person_months[(row.cpr, (index % 12) + 1)],
                employer=employers[row.cvr],
                amount=amount,
            )
            for row in rows
            for index, amount in enumerate(row.amounts)
        ]
        ASalaryReport.objects.filter(person_month__person_year__year=year).delete()
        ASalaryReport.objects.bulk_create(a_salary_reports)
        self.stdout.write(f"Created {len(a_salary_reports)} ASalaryReport objects")
