# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import random
from decimal import Decimal

import pytz
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
    TaxScope,
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


def set_history_date(obj, date):
    entry = obj.history.all().order_by("-history_date")[0]
    entry.history_date = pytz.utc.localize(
        datetime.datetime(date.year, date.month, date.day, 0, 0, 0)
    )
    entry.save()


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
            Person.objects.update_or_create(
                cpr=bruce.cpr, defaults={"name": "Bruce Lee"}
            )[0]: [10000]
            * 12,
            # Person who is paused
            Person.objects.update_or_create(
                cpr="0301011991",
                defaults={"paused": True, "name": "Person who is paused"},
            )[0]: [10000]
            * 12,
            # Person who is in quarantine (because he earns nearly too much)
            Person.objects.update_or_create(
                cpr="0401011991", defaults={"name": "Person who is in quarantine"}
            )[0]: [490_000 / 12]
            * 12,
            # Person who gets nothing because he earns too much
            Person.objects.update_or_create(
                cpr="0501011991", defaults={"name": "Person who earns too much"}
            )[0]: [5_000_000 / 12]
            * 12,
        }

        for person, salary in persons.items():
            set_history_date(person, dates[0])
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
                set_history_date(person_month, date)
                MonthlyIncomeReport.objects.update_or_create(
                    person_month=person_month,
                    month=month,
                    year=year,
                    defaults={"salary_income": Decimal(salary[date.month - 1])},
                )

                person_year.tax_scope = random.choice(
                    [
                        TaxScope.FULDT_SKATTEPLIGTIG,
                        TaxScope.DELVIST_SKATTEPLIGTIG,
                        TaxScope.FORSVUNDET_FRA_MANDTAL,
                    ]
                )

                person_year.save()
                set_history_date(person_year, date)
            person_year.tax_scope = TaxScope.FULDT_SKATTEPLIGTIG
            person_year.save()

            call_command(ManagementCommands.ESTIMATE_INCOME, cpr=person.cpr)

            last_month = get_last_month(datetime.date.today())
            month_before_last_month = get_last_month(last_month)
            for date in dates:

                call_command(
                    ManagementCommands.CALCULATE_BENEFIT,
                    date.year,
                    date.month,
                    cpr=person.cpr,
                )

                if date < month_before_last_month:

                    person_month = PersonMonth.objects.get(
                        person_year__person=person,
                        month=date.month,
                        person_year__year__year=date.year,
                    )

                    if person_month.benefit_calculated > 0:

                        prisme_batch, _ = PrismeBatch.objects.update_or_create(
                            export_date=datetime.date(date.year, date.month, 12),
                            defaults={"status": "sent", "prefix": 1},
                        )

                        PrismeBatchItem.objects.update_or_create(
                            prisme_batch=prisme_batch,
                            person_month=person_month,
                            defaults={
                                "status": "posted",
                                "paused": person_month.person_year.person.paused,
                                "g68_content": (
                                    "000G6800004011&020900&0300&"
                                    "07000000000000000000&0800000031700&"
                                    "09+&1002&1100000101001111&1220250414&"
                                    "16202504080080400004&"
                                    "1700000000000027100004&40www.suila.gl takuuk"
                                ),
                            },
                        )
                        person_month.benefit_transferred = (
                            person_month.benefit_calculated
                        )
                        person_month.save()
