# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from decimal import Decimal

import numpy as np
from common.utils import calculate_stability_score_for_entire_year

from suila.management.commands.common import SuilaBaseCommand
from suila.models import PersonYear


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose(f"Calculating stability score for {kwargs['year']}")

        person_years = PersonYear.objects.filter(year__year=kwargs["year"])
        if not person_years:
            return

        df_stability_score = calculate_stability_score_for_entire_year(kwargs["year"])

        person_year_objects_to_update = []
        for person_year in person_years:
            if person_year.person.cpr in df_stability_score.index:

                stability_score_a: np.int64 = df_stability_score.loc[
                    person_year.person.cpr, "A"
                ]
                stability_score_b: np.int64 = df_stability_score.loc[
                    person_year.person.cpr, "B"
                ]

                if not np.isnan(stability_score_a):
                    person_year.stability_score_a = Decimal(stability_score_a.item())
                if not np.isnan(stability_score_b):
                    person_year.stability_score_b = Decimal(stability_score_b.item())

                person_year_objects_to_update.append(person_year)

        PersonYear.objects.bulk_update(
            person_year_objects_to_update,
            ["stability_score_a", "stability_score_b"],
            batch_size=1000,
        )

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
