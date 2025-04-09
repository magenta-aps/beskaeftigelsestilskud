# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import patch

import numpy as np
import pandas as pd
from common.tests.test_utils import BaseTestCase

from suila.models import PersonYear


class CalculateStabilityScoreTest(BaseTestCase):

    def test_calculate_stability_score(self):

        for person_year in PersonYear.objects.all():
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)

        self.call_command("calculate_stability_score", self.year, verbosity=3)
        for person_year in PersonYear.objects.filter(year__year=self.year.year + 1):
            self.assertGreater(person_year.stability_score_a, 0)
            self.assertGreater(person_year.stability_score_b, 0)

    @patch(
        "suila.management.commands.calculate_stability_score."
        "calculate_stability_score_for_entire_year"
    )
    def test_calculate_stability_score_nan_stability_scores(
        self, calculate_stability_score_for_entire_year
    ):
        df = pd.DataFrame(index=["1234567890", "1234567891"])

        df["A"] = [np.nan, np.nan]
        df["B"] = [np.nan, np.nan]

        calculate_stability_score_for_entire_year.return_value = df
        self.call_command("calculate_stability_score", self.year)

        for person_year in PersonYear.objects.all():
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)

    @patch(
        "suila.management.commands.calculate_stability_score."
        "calculate_stability_score_for_entire_year"
    )
    def test_calculate_stability_score_missing_person(
        self, calculate_stability_score_for_entire_year
    ):
        df = pd.DataFrame(index=["1234567890"])

        df["A"] = [1]
        df["B"] = [1]

        calculate_stability_score_for_entire_year.return_value = df
        self.call_command("calculate_stability_score", self.year)

        for person_year in PersonYear.objects.filter(
            person__cpr="1234567890", year__year=self.year.year + 1
        ):
            self.assertEqual(person_year.stability_score_a, 1)
            self.assertEqual(person_year.stability_score_b, 1)

        for person_year in PersonYear.objects.filter(
            person__cpr="1234567891", year__year=self.year.year + 1
        ):
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)
