# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from common.utils import isnan
from simple_history.utils import bulk_update_with_history

from suila.benefit import calculate_benefit
from suila.management.commands.common import SuilaBaseCommand
from suila.models import PersonMonth


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1

        month = kwargs["month"]
        year = kwargs["year"]

        self._write_verbose(f"Calculating benefit for {year}-{month}")

        cols_to_update = [
            "benefit_calculated",
            "prior_benefit_transferred",
            "estimated_year_benefit",
            "actual_year_benefit",
            "estimated_year_result",
        ]

        benefit = calculate_benefit(month, year, kwargs["cpr"])

        person_month_qs = PersonMonth.objects.filter(
            person_year__year__year=year,
            month=month,
            prismebatchitem__isnull=True,
        ).select_related("person_year__person")

        person_months_to_update = []

        for person_month in person_month_qs:
            cpr = person_month.person_year.person.cpr
            if cpr in benefit.index:
                for col in cols_to_update:
                    value = benefit.loc[cpr, col]
                    if isnan(value):
                        value = None
                    setattr(person_month, col, value)
                person_months_to_update.append(person_month)
        bulk_update_with_history(
            person_months_to_update,
            PersonMonth,
            cols_to_update,
            batch_size=1000,
        )

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
