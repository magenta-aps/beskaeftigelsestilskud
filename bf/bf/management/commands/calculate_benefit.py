# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.core.management.base import BaseCommand

from bf.models import PersonMonth


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)

    def handle(self, *args, **kwargs):

        months = PersonMonth.objects.filter(
            person_year__year__year=kwargs["year"], month=kwargs["month"]
        ).select_related("person_year")
        for person_month in months:
            person_month.calculate_benefit()
            person_month.save()
