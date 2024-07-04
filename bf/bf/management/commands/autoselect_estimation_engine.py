# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from collections import defaultdict

from data_analysis.models import IncomeEstimate
from django.core.management.base import BaseCommand

from bf.models import Person


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
            person.preferred_estimation_engine = min(averages, key=averages.get)
            person.save(update_fields=("preferred_estimation_engine",))
