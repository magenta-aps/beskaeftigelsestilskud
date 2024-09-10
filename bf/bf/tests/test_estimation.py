# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal

from django.test import TestCase

from bf.estimation import SelfReportedEngine
from bf.exceptions import IncomeTypeUnhandledByEngine
from bf.models import (
    IncomeType,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    Year,
)


class TestSelfReportedEngine(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year = Year.objects.create(year=2024)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
        )
        cls.person_month = PersonMonth.objects.create(
            person_year=cls.person_year, month=1, import_date=date.today()
        )
        cls.assessment = PersonYearAssessment.objects.create(
            person_year=cls.person_year,
            renteindtægter=Decimal(0),
            uddannelsesstøtte=Decimal(0),
            honorarer=Decimal(0),
            underholdsbidrag=Decimal(0),
            andre_b=Decimal(0),
            brutto_b_før_erhvervsvirk_indhandling=Decimal(0),
            erhvervsindtægter_sum=Decimal(50000),
            e2_indhandling=Decimal(20000),
            brutto_b_indkomst=Decimal(70000),
        )

    def test_cannot_calculate_a(self):
        with self.assertRaises(IncomeTypeUnhandledByEngine):
            SelfReportedEngine.estimate(self.person_month, [], IncomeType.A)

    def test_calculate_b(self):
        income_estimate = SelfReportedEngine.estimate(
            self.person_month, [], IncomeType.B
        )
        self.assertIsNotNone(income_estimate)
        self.assertEqual(income_estimate.engine, "SelfReportedEngine")
        self.assertEqual(income_estimate.income_type, IncomeType.B)
        self.assertEqual(income_estimate.person_month, self.person_month)
        self.assertEqual(income_estimate.estimated_year_result, Decimal(50000))
