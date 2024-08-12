# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from collections import defaultdict

from django.core.management.base import BaseCommand

from bf.models import IncomeEstimate, Person


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        for person in Person.objects.all():
            estimates = IncomeEstimate.objects.filter(
                person_month__person_year__person=person
            )
            offsets = defaultdict(list)
            for estimate in estimates:
                offsets[estimate.engine].append(estimate.offset)
            averages = {
                engine: sum(current_offsets) / len(current_offsets)
                for engine, current_offsets in offsets.items()
            }
            if averages:
                person.preferred_estimation_engine = min(averages, key=averages.get)
                person.save(update_fields=("preferred_estimation_engine",))
            else:
                income_sums = {
                    person_year.year.year: str(person_year.amount_sum)
                    for person_year in person.personyear_set.all()
                }
                self.stdout.write(
                    f"Could not auto-select preferred estimation engine for {person} (id: {person.pk}) (income: {income_sums})"
                )
