# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from suila.models import Person, PersonMonth, PersonYear, Year

User = get_user_model()


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

        this_year = datetime.now().year
        this_month = datetime.now().month

        bruce_person, _ = Person.objects.update_or_create(cpr=bruce.cpr)

        for year in [this_year - 1, this_year]:
            year_obj, _ = Year.objects.update_or_create(year=year)

            person_year, _ = PersonYear.objects.update_or_create(
                person=bruce_person, year=year_obj
            )

            months_to_create = (
                range(1, this_month + 1) if year == this_year else range(1, 13)
            )

            for month in months_to_create:
                PersonMonth.objects.update_or_create(
                    month=month, person_year=person_year, import_date=date.today()
                )
