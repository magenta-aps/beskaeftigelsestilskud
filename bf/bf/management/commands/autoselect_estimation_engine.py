# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from collections import defaultdict

from django.core.management.base import BaseCommand

from bf.models import IncomeType, Person, PersonYearEstimateSummary


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        for person in Person.objects.all():
            has_set = False
            for income_type in IncomeType:
                summaries = PersonYearEstimateSummary.objects.filter(
                    person_year__person=person,
                    income_type=income_type,
                )
                rmses = defaultdict(list)
                for summary in summaries:
                    if summary.rmse_percent:
                        rmses[summary.estimation_engine].append(summary.rmse_percent)

                # If there are multiple years in the dataset:
                # Take an average over all years
                for estimation_engine, rmse_results in rmses.items():
                    rmses[estimation_engine] = [sum(rmse_results) / len(rmse_results)]

                if rmses:
                    field = f"preferred_estimation_engine_{income_type.value.lower()}"
                    setattr(person, field, min(rmses, key=rmses.get))
                    person.save(update_fields=(field,))
                    has_set = True
            if not has_set:
                income_sums = {
                    person_year.year.year: str(person_year.amount_sum)
                    for person_year in person.personyear_set.all()
                }
                self.stdout.write(
                    "Could not auto-select preferred estimation engine "
                    f"for {person} (id: {person.pk}) (income: {income_sums})"
                )
