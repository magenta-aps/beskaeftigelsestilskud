# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from common.utils import calculate_benefit, isnan

from bf.management.commands.common import BfBaseCommand
from bf.models import PersonMonth


class Command(BfBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose(f"Calculating benefit for {kwargs['year']}")

        month = kwargs["month"]
        year = kwargs["year"]

        cols_to_update = [
            "benefit_paid",
            "prior_benefit_paid",
            "estimated_year_benefit",
            "actual_year_benefit",
            "estimated_year_result",
        ]

        if month and month >= 1 and month <= 12:
            month_range = [month]
        else:
            month_range = range(1, 13)

        for month_number in month_range:
            benefit = calculate_benefit(month_number, year, kwargs["cpr"])

            person_months_to_update = []
            for person_month in PersonMonth.objects.filter(
                person_year__year__year=kwargs["year"], month=month_number
            ).select_related("person_year__person"):
                cpr = person_month.person_year.person.cpr
                if cpr in benefit.index:
                    for col in cols_to_update:
                        value = benefit.loc[cpr, col]
                        if isnan(value):
                            value = None
                        setattr(person_month, col, value)
                    person_months_to_update.append(person_month)

            PersonMonth.objects.bulk_update(
                person_months_to_update,
                cols_to_update,
                batch_size=1000,
            )

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
