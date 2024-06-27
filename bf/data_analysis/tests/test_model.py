# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from data_analysis.models import IncomeEstimate

from bf.tests.test_model import ModelTest


class EstimationTest(ModelTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.result1 = IncomeEstimate.objects.create(
            engine="InYearExtrapolationEngine",
            person_month=cls.month1,
            estimated_year_result=1200,
            actual_year_result=1400,
        )

    def test_str(self):
        self.assertEqual(
            str(self.result1), "InYearExtrapolationEngine (Jens Hansen (2024/1))"
        )

    def test_absdiff(self):
        self.assertEqual(self.result1.absdiff, 200)

    def test_offset(self):
        self.assertEqual(self.result1.offset, 200 / 1400)

    def test_annotate_month(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(IncomeEstimate.annotate_month(qs).first().f_month, 1)

    def test_annotate_year(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(IncomeEstimate.annotate_year(qs).first().f_year, 2024)

    def test_annotate_person_year(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(
            IncomeEstimate.annotate_person_year(qs).first().f_person_year,
            self.person_year.pk,
        )
