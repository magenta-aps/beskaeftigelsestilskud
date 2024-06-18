# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from data_analysis.models import CalculationResult

from bf.tests.test_model import ModelTest


class CalculationResultTest(ModelTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.result1 = CalculationResult.objects.create(
            engine="InYearExtrapolationEngine",
            a_salary_report=cls.report1,
            calculated_year_result=1200,
            actual_year_result=1400,
        )

    def test_shortcuts(self):
        self.assertEqual(self.result1.absdiff, 200)
