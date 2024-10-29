# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal
from typing import Dict, List, TextIO

from common.utils import camelcase_to_snakecase
from django.db import transaction

from bf.integrations.eskat.responses.data_models import MonthlyIncome
from bf.models import (
    Employer,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)


class Handler:

    @classmethod
    def create_person_years(
        cls, year: int, cprs: List[str], out: TextIO
    ) -> Dict[str, PersonYear] | None:

        # Create or get Year objects
        year_obj, _ = Year.objects.get_or_create(year=year)

        # Create or update Person objects
        persons = {cpr: Person(cpr=cpr, name=cpr) for cpr in set(cprs)}
        Person.objects.bulk_create(
            persons.values(),
            update_conflicts=True,
            update_fields=("cpr", "name"),
            unique_fields=("cpr",),
        )
        out.write(f"Processed {len(persons)} Person objects")

        # Create or update PersonYear objects
        person_years = {
            person.cpr: PersonYear(person=person, year=year_obj)
            for person in persons.values()
        }
        PersonYear.objects.bulk_create(
            person_years.values(),
            update_conflicts=True,
            update_fields=("person", "year"),
            unique_fields=("person", "year"),
        )
        out.write(f"Processed {len(person_years)} PersonYear objects")
        return person_years


class MonthlyIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> MonthlyIncome:
        return MonthlyIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: List["MonthlyIncome"], out: TextIO
    ):
        with transaction.atomic():

            # TODO: vi får ikke en cvr fra eskat,
            # så dette er en dummy indtil vi ved mere
            employer, _ = Employer.objects.get_or_create(cvr="11111111")

            # Create or update Year object
            person_years = cls.create_person_years(
                year, [item.cpr for item in items], out
            )
            if person_years:

                # Create or update PersonMonth objects
                person_months = {}
                for person_year in person_years.values():
                    for month in range(1, 13):
                        person_month = PersonMonth(
                            person_year=person_year,
                            month=month,
                            import_date=date.today(),
                            amount_sum=Decimal(0),
                        )
                        key = (person_year.person.cpr, month)
                        person_months[key] = person_month
                PersonMonth.objects.bulk_create(
                    person_months.values(),
                    update_conflicts=True,
                    update_fields=("import_date",),
                    unique_fields=("person_year", "month"),
                )
                out.write(f"Processed {len(person_months)} PersonMonth objects")

                # Create MonthlyAIncomeReport objects
                # (existing objects for this year will be deleted!)
                a_income_reports = []
                for item in items:
                    # TODO: Hvilke felter tæller som A-indkomst?
                    for index, amount in enumerate(
                        [item.salary_income, item.alimony_income]
                    ):
                        if amount is not None:
                            amount = Decimal(amount)
                            person_month = person_months[(item.cpr, (index % 12) + 1)]
                            a_income_reports.append(
                                MonthlyAIncomeReport(
                                    person_month=person_month,
                                    employer=employer,
                                    amount=amount,
                                )
                            )
                            person_month.amount_sum += amount
                            person_month.save(update_fields=("amount_sum",))
                MonthlyAIncomeReport.objects.filter(
                    person_month__person_year__year=year
                ).delete()
                MonthlyAIncomeReport.objects.bulk_create(a_income_reports)
                out.write(
                    f"Created {len(a_income_reports)} MonthlyAIncomeReport objects"
                )

                # Create MonthlyBIncomeReport objects
                # (existing objects for this year will be deleted!)
                b_income_reports = []
                for item in items:
                    # TODO: Hvilke felter tæller som B-indkomst?
                    for index, amount in enumerate(
                        [item.foreign_pension_income, item.other_pension_income]
                    ):
                        if amount is not None:
                            amount = Decimal(amount)
                            person_month = person_months[(item.cpr, (index % 12) + 1)]
                            b_income_reports.append(
                                MonthlyBIncomeReport(
                                    person_month=person_month,
                                    trader=employer,
                                    amount=amount,
                                )
                            )
                            person_month.amount_sum += amount
                            person_month.save(update_fields=("amount_sum",))
                MonthlyBIncomeReport.objects.filter(
                    person_month__person_year__year=year
                ).delete()
                MonthlyBIncomeReport.objects.bulk_create(b_income_reports)
                out.write(
                    f"Created {len(b_income_reports)} MonthlyBIncomeReport objects"
                )