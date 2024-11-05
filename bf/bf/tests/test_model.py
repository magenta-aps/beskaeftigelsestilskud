# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from bf.data import MonthlyIncomeData
from bf.models import (
    Employer,
    FinalSettlement,
    IncomeEstimate,
    IncomeType,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    StandardWorkBenefitCalculationMethod,
    Year,
)


class ModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        cls.year = Year.objects.create(year=2024, calculation_method=cls.calc)
        cls.year2 = Year.objects.create(year=2025)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
        )
        cls.person_year2 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year2,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
        )
        cls.month1 = PersonMonth.objects.create(
            person_year=cls.person_year, month=1, import_date=date.today()
        )
        cls.month2 = PersonMonth.objects.create(
            person_year=cls.person_year, month=2, import_date=date.today()
        )
        cls.month3 = PersonMonth.objects.create(
            person_year=cls.person_year, month=3, import_date=date.today()
        )
        cls.month4 = PersonMonth.objects.create(
            person_year=cls.person_year, month=4, import_date=date.today()
        )
        cls.month12 = PersonMonth.objects.create(
            person_year=cls.person_year, month=12, import_date=date.today()
        )
        cls.year2month1 = PersonMonth.objects.create(
            person_year=cls.person_year2, month=1, import_date=date.today()
        )
        cls.employer1 = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )
        cls.employer2 = Employer.objects.create(
            name="Ronnis Rejer",
            cvr=87654321,
        )
        cls.report1 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month1,
            salary_income=Decimal(10000),
            month=cls.month1.month,
            year=cls.year.year,
            person=cls.person,
        )
        cls.report2 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month2,
            salary_income=Decimal(11000),
            month=cls.month2.month,
            year=cls.year.year,
            person=cls.person,
        )
        cls.report3 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month3,
            salary_income=Decimal(12000),
            month=cls.month3.month,
            year=cls.year.year,
            person=cls.person,
        )
        cls.report4 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month4,
            salary_income=Decimal(13000),
            month=cls.month4.month,
            year=cls.year.year,
            person=cls.person,
        )
        cls.report5 = MonthlyBIncomeReport.objects.create(
            trader=cls.employer2,
            person_month=cls.month1,
            amount=Decimal(15000),
            month=cls.month1.month,
            year=cls.year.year,
            person=cls.person,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month1,
            estimated_year_result=12 * 10000,
            actual_year_result=12 * 10000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month1,
            estimated_year_result=12 * 15000,
            actual_year_result=12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.B,
        )
        cls.report6 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month2,
            salary_income=Decimal(12000),
            month=cls.month2.month,
            year=cls.year.year,
            person=cls.person,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month2,
            estimated_year_result=6 * (10000 + 11000) + 6 * (15000 + 12000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report7 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month3,
            salary_income=Decimal(10000),
            month=cls.month3.month,
            year=cls.year.year,
            person=cls.person,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month3,
            estimated_year_result=4 * (10000 + 11000 + 12000)
            + 4 * (15000 + 12000 + 10000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report8 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month4,
            salary_income=Decimal(8000),
            month=cls.month4.month,
            year=cls.year.year,
            person=cls.person,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month4,
            estimated_year_result=3 * (10000 + 11000 + 12000 + 13000)
            + 3 * (15000 + 12000 + 10000 + 8000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report9 = MonthlyAIncomeReport.objects.create(
            employer=cls.employer2,
            person_month=cls.year2month1,
            salary_income=Decimal(8000),
            month=cls.year2month1.month,
            year=cls.year2.year,
            person=cls.person,
        )
        # No IncomeEstimate

        cls.final_settlement = FinalSettlement.objects.create(
            person_year=cls.person_year,
            skattemæssigt_resultat=Decimal(13000),
        )


class TestStandardWorkBenefitCalculationMethod(ModelTest):

    def test_low(self):
        self.assertEqual(self.calc.calculate(Decimal("0")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("25000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("58000")), Decimal(0))

    def test_ramp_up(self):
        self.assertEqual(self.calc.calculate(Decimal("68000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("70000")), Decimal("350.00"))
        self.assertEqual(self.calc.calculate(Decimal("130000")), Decimal("10850.00"))
        self.assertEqual(self.calc.calculate(Decimal("158000")), Decimal("15750.00"))

    def test_plateau(self):
        self.assertEqual(self.calc.calculate(Decimal("158000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("200000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("250000")), Decimal("15750.00"))

    def test_ramp_down(self):
        self.assertEqual(self.calc.calculate(Decimal("250000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("261000")), Decimal("15057.00"))
        self.assertEqual(self.calc.calculate(Decimal("340000")), Decimal("10080.00"))
        self.assertEqual(self.calc.calculate(Decimal("490000")), Decimal("630.00"))
        self.assertEqual(self.calc.calculate(Decimal("500000")), Decimal(0))

    def test_high(self):
        self.assertEqual(self.calc.calculate(Decimal("500000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("750000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("1000000")), Decimal(0))

    def test_graph_points(self):
        self.assertEqual(
            self.calc.graph_points,
            [
                (Decimal("0"), Decimal("0")),
                (Decimal("68000.00"), Decimal("0")),
                (Decimal("158000.00"), Decimal("15750.00")),
                (Decimal("250000.00"), Decimal("15750.00")),
                (Decimal("500000.00"), Decimal("0")),
            ],
        )


pitu_client_mock = MagicMock()
pitu_client_mock.get_person_info.return_value = {"civilstand": "G", "stedkode": "001"}

PituClient_mock = MagicMock()
PituClient_mock.from_settings.return_value = pitu_client_mock


class TestPerson(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.person), "Jens Hansen")


class TestPersonYear(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.person_year), "Jens Hansen (2024)")

    def test_next(self):
        self.assertEqual(self.person_year.next, self.person_year2)
        self.assertIsNone(self.person_year2.next)

    def test_prev(self):
        self.assertEqual(self.person_year2.prev, self.person_year)
        self.assertIsNone(self.person_year.prev)

    def test_b_income(self):
        self.assertEqual(self.person_year.b_income, Decimal(13000))
        self.assertIsNone(self.person_year2.b_income)


class TestPersonMonth(ModelTest):

    def test_shortcuts(self):
        self.assertEqual(self.month1.year, 2024)

    def test_string_methods(self):
        self.assertEqual(str(self.month1), "Jens Hansen (2024/1)")

    def test_amount_sum(self):
        self.assertEqual(self.month1.amount_sum, Decimal(10000 + 15000))
        self.assertEqual(self.month2.amount_sum, Decimal(11000 + 12000))
        self.assertEqual(self.month3.amount_sum, Decimal(12000 + 10000))
        self.assertEqual(self.month4.amount_sum, Decimal(13000 + 8000))

    def test_next(self):
        self.assertEqual(self.month1.next, self.month2)
        self.assertEqual(self.month12.next, self.year2month1)
        self.assertIsNone(self.year2month1.next)

    def test_prev(self):
        self.assertEqual(self.month2.prev, self.month1)
        self.assertEqual(self.year2month1.prev, self.month12)
        self.assertIsNone(self.month1.prev)
        self.assertIsNone(self.month12.prev)


class TestEmployer(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.employer1), "Fredes Fisk (12345678)")


class TestIncomeReport(ModelTest):

    def test_shortcuts(self):
        self.assertEqual(self.report1.person_year, self.person_year)
        self.assertEqual(self.report1.person, self.person)
        self.assertEqual(self.report1.year, 2024)
        self.assertEqual(self.report1.month, 1)

    def test_string_methods(self):
        self.assertEqual(
            str(self.report1), "Jens Hansen (2024/1) | Fredes Fisk (12345678)"
        )
        self.assertEqual(
            str(self.report5), "Jens Hansen (2024/1) | Ronnis Rejer (87654321)"
        )

    def test_annotate_month(self):
        qs = MonthlyAIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(MonthlyAIncomeReport.annotate_month(qs).first().f_month, 1)

    def test_annotate_year(self):
        qs = MonthlyAIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(MonthlyAIncomeReport.annotate_year(qs).first().f_year, 2024)

    def test_annotate_person_year(self):
        qs = MonthlyAIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(
            MonthlyAIncomeReport.annotate_person_year(qs).first().f_person_year,
            self.person_year.pk,
        )

    def test_annotate_person(self):
        qs = MonthlyAIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(
            MonthlyAIncomeReport.annotate_person(qs).first().f_person,
            self.person.pk,
        )

    def test_data_amount(self):
        data = MonthlyIncomeData(
            month=6,
            year=2024,
            a_amount=Decimal(15000),
            b_amount=Decimal(5000),
            person_pk=1,
            person_month_pk=1,
            person_year_pk=1,
        )
        self.assertEqual(data.amount, Decimal(20000))


class EstimationTest(ModelTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.result1, _ = IncomeEstimate.objects.update_or_create(
            engine="InYearExtrapolationEngine",
            person_month=cls.month1,
            income_type=IncomeType.A,
            defaults={
                "estimated_year_result": 1200,
                "actual_year_result": 1400,
            },
        )
        cls.result2, _ = IncomeEstimate.objects.update_or_create(
            engine="InYearExtrapolationEngine",
            person_month=cls.month1,
            income_type=IncomeType.B,
            defaults={
                "estimated_year_result": 150,
                "actual_year_result": 200,
            },
        )

    def test_str(self):
        self.assertEqual(
            str(self.result1), "InYearExtrapolationEngine (Jens Hansen (2024/1)) (A)"
        )

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

    def test_qs_offset(self):
        qs = IncomeEstimate.objects.filter(pk__in=[self.result1.pk, self.result2.pk])
        self.assertEqual(IncomeEstimate.qs_offset(qs), Decimal(250 / 1600))
