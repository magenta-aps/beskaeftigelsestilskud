import csv
from dataclasses import dataclass
from datetime import date

from django.core.management.base import BaseCommand

from bf.models import Company, MonthIncome, Person


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
    jan: int | None
    feb: int | None
    mar: int | None
    apr: int | None
    maj: int | None
    jun: int | None
    jul: int | None
    aug: int | None
    sep: int | None
    okt: int | None
    nov: int | None
    dec: int | None

    @classmethod
    def from_csv_row(cls, row):
        if len(row) > 3:
            return cls(
                cpr=int(list_get(row, 0)),
                arbejdsgiver=list_get(row, 1),
                cvr=int(list_get(row, 2)),
                jan=list_get(row, 3) or 0,
                feb=list_get(row, 4) or 0,
                mar=list_get(row, 5) or 0,
                apr=list_get(row, 6) or 0,
                maj=list_get(row, 7) or 0,
                jun=list_get(row, 8) or 0,
                jul=list_get(row, 9) or 0,
                aug=list_get(row, 10) or 0,
                sep=list_get(row, 11) or 0,
                okt=list_get(row, 12) or 0,
                nov=list_get(row, 13) or 0,
                dec=list_get(row, 14) or 0,
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
            print(line)
            if line:
                person, _ = Person.objects.get_or_create(cpr=line.cpr, defaults={})
                company, _ = Company.objects.get_or_create(cvr=line.cvr, defaults={})
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=1,
                    amount=line.jan,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=2,
                    amount=line.feb,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=3,
                    amount=line.mar,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=4,
                    amount=line.apr,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=5,
                    amount=line.maj,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=6,
                    amount=line.jun,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=7,
                    amount=line.jul,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=8,
                    amount=line.aug,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=9,
                    amount=line.sep,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=10,
                    amount=line.okt,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=11,
                    amount=line.nov,
                    year=year,
                )
                MonthIncome.objects.create(
                    person=person,
                    company=company,
                    month=12,
                    amount=line.dec,
                    year=year,
                )
