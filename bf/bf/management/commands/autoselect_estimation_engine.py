# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from collections import defaultdict

from django.core.management.base import BaseCommand

from bf.models import Person, PersonYearEstimateSummary


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        for person in Person.objects.all():

            summaries = PersonYearEstimateSummary.objects.filter(
                person_year__person=person
            )

            rmses = defaultdict(list)
            for summary in summaries:
                if summary.rmse_percent:
                    rmses[summary.estimation_engine].append(summary.rmse_percent)

            if rmses:
                person.preferred_estimation_engine = min(rmses, key=rmses.get)
                person.save(update_fields=("preferred_estimation_engine",))
