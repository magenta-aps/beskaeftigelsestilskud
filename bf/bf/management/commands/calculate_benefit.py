# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.core.management.base import BaseCommand

from bf.exceptions import EstimationEngineUnset
from bf.models import PersonMonth


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--cpr", type=int)

    def handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1

        self._write_verbose(f"Calculating benefit for {kwargs['year']}")

        if kwargs["cpr"]:
            months = PersonMonth.objects.filter(
                person_year__year__year=kwargs["year"],
                person_year__person__cpr=kwargs["cpr"],
            )
        else:
            months = PersonMonth.objects.filter(
                person_year__year__year=kwargs["year"],
            )
        months = months.filter(incomeestimate__isnull=False)

        month = kwargs["month"]
        if month and month >= 1 and month <= 12:
            months = months.filter(month=month)

        months = months.select_related("person_year").order_by(
            "person_year__person", "month"
        )
        for person_month in months:
            try:
                person_month.calculate_benefit()
                person_month.save()
            except EstimationEngineUnset as e:
                self._write_verbose(str(e))

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
