# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from suila.models import (
    ManagementCommands,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    Year,
)

User = get_user_model()


def get_next_month(date_obj):

    month = date_obj.month + 1 if date_obj.month < 12 else 1
    year = date_obj.year + 1 if month == 1 else date_obj.year
    return datetime.date(year, month, 1)


def get_last_month(date_obj):

    month = date_obj.month - 1 if date_obj.month > 1 else 12
    year = date_obj.year - 1 if month == 12 else date_obj.year

    return datetime.date(year, month, 1)


def get_dates_to_create():
    """
    Return a couple of months before and a month after today's date
    """
    today = datetime.date.today()

    # Create the current month
    dates = [datetime.date(today.year, today.month, 1)]

    # Create the upcoming month
    for i in range(1):
        dates.append(get_next_month(dates[-1]))

    # Create the past 12 months
    for i in range(12):
        dates.insert(0, get_last_month(dates[0]))

    return dates


class Command(BaseCommand):

    def handle(self, *args, **options):

        # Create a user without a person-year
        anders, _ = User.objects.update_or_create(
            username="anders",
            defaults={"first_name": "Anders", "last_name": "And", "cpr": "0201011991"},
        )

        # Create a user with a couple of person-year
        bruce, _ = User.objects.update_or_create(
            username="bruce",
            defaults={"first_name": "Bruce", "last_name": "Lee", "cpr": "0101011991"},
        )

        bruce.set_password("bruce")
        anders.set_password("anders")

        anders.save()
        bruce.save()

        dates = get_dates_to_create()

        persons = {
            # Normal person
            Person.objects.update_or_create(cpr=bruce.cpr)[0]: [10000] * 12,
            # Person who is paused
            Person.objects.update_or_create(
                cpr="0301011991", defaults={"paused": True}
            )[0]: [10000]
            * 12,
            # Person who is in quarantine (because he earns nearly too much)
            Person.objects.update_or_create(cpr="0401011991")[0]: [490_000 / 12] * 12,
        }

        for person, salary in persons.items():
            for date in dates:
                year = date.year
                month = date.month
                year_obj, _ = Year.objects.update_or_create(year=year)

                person_year, _ = PersonYear.objects.update_or_create(
                    person=person, year=year_obj
                )

                person_month, _ = PersonMonth.objects.update_or_create(
                    month=month,
                    person_year=person_year,
                    defaults={"import_date": datetime.date.today()},
                )
                MonthlyIncomeReport.objects.update_or_create(
                    person_month=person_month,
                    month=month,
                    year=year,
                    defaults={"salary_income": Decimal(salary[date.month - 1])},
                )

            call_command(ManagementCommands.ESTIMATE_INCOME, cpr=person.cpr)

            last_month = get_last_month(datetime.date.today())
            month_before_last_month = get_last_month(last_month)
            for date in dates:

                call_command(
                    ManagementCommands.CALCULATE_BENEFIT,
                    date.year,
                    cpr=person.cpr,
                    month=date.month,
                )

                if date < month_before_last_month:
                    prisme_batch, _ = PrismeBatch.objects.update_or_create(
                        export_date=datetime.date(date.year, date.month, 12),
                        defaults={"status": "sent", "prefix": 1},
                    )

                    person_month = PersonMonth.objects.get(
                        person_year__person=person,
                        month=date.month,
                        person_year__year__year=date.year,
                    )

                    PrismeBatchItem.objects.update_or_create(
                        prisme_batch=prisme_batch,
                        person_month=person_month,
                        defaults={
                            "status": "posted",
                            "paused": person_month.person_year.person.paused,
                        },
                    )
