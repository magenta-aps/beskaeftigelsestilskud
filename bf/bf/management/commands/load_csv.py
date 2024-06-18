# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
from dataclasses import dataclass
from datetime import date
from typing import List

from django.core.management.base import BaseCommand

from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear


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
                amounts=[
                    list_get(row, 3) or 0,
                    list_get(row, 4) or 0,
                    list_get(row, 5) or 0,
                    list_get(row, 6) or 0,
                    list_get(row, 7) or 0,
                    list_get(row, 8) or 0,
                    list_get(row, 9) or 0,
                    list_get(row, 10) or 0,
                    list_get(row, 11) or 0,
                    list_get(row, 12) or 0,
                    list_get(row, 13) or 0,
                    list_get(row, 14) or 0,
                ],
            )


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file", type=str)
        parser.add_argument("--count", type=int)
        parser.add_argument("--year", type=int)

    def handle(self, *args, **kwargs):
        with open(kwargs["file"]) as input_stream:
            count = kwargs.get("count")
            year = kwargs.get("year") or date.today().year
            self._read_csv(input_stream, year, count)

    def _read_csv(self, input_stream, year, count=None):
        reader = csv.reader(input_stream, delimiter=";")

        next(reader)  # skip csv header

        for i, row in enumerate(reader):
            if count is not None and i > count:
                break
            # We are not yet at last line in file. Parse it as a regular item
            line = IndkomstCSVFileLine.from_csv_row(row)
            if line:
                person, _ = Person.objects.get_or_create(
                    name=line.cpr, cpr=line.cpr, defaults={}
                )
                person_year, _ = PersonYear.objects.get_or_create(
                    person=person, year=year
                )
                employer, _ = Employer.objects.get_or_create(cvr=line.cvr, defaults={})
                for month, amount in enumerate(line.amounts, 1):
                    person_month, _ = PersonMonth.objects.get_or_create(
                        person_year=person_year,
                        month=month,
                        defaults={
                            "import_date": date.today(),
                        },
                    )
                    ASalaryReport.objects.update_or_create(
                        person_month=person_month,
                        employer=employer,
                        defaults={
                            "amount": amount,
                        },
                    )
            print(i, end="\r")
