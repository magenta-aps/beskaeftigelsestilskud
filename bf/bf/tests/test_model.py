# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from data_analysis.models import CalculationResult
from django.test import TestCase

from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear


class ModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")
        cls.year = PersonYear.objects.create(
            person=cls.person,
            year=2024,
        )
        cls.year2 = PersonYear.objects.create(
            person=cls.person,
            year=2025,
        )
        cls.month1 = PersonMonth.objects.create(
            person_year=cls.year, month=1, import_date=date.today()
        )
        cls.month2 = PersonMonth.objects.create(
            person_year=cls.year, month=2, import_date=date.today()
        )
        cls.month3 = PersonMonth.objects.create(
            person_year=cls.year, month=3, import_date=date.today()
        )
        cls.month4 = PersonMonth.objects.create(
            person_year=cls.year, month=4, import_date=date.today()
        )
        cls.month5 = PersonMonth.objects.create(
            person_year=cls.year2, month=1, import_date=date.today()
        )
        cls.employer1 = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )
        cls.employer2 = Employer.objects.create(
            name="Ronnis Rejer",
            cvr=87654321,
        )
        cls.report1 = ASalaryReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month1,
            amount=100,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report1,
            calculated_year_result=12 * 100,
        )
        cls.report2 = ASalaryReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month2,
            amount=110,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report2,
            calculated_year_result=6 * (100 + 110),
        )
        cls.report3 = ASalaryReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month3,
            amount=120,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report3,
            calculated_year_result=4 * (100 + 110 + 120),
        )
        cls.report4 = ASalaryReport.objects.create(
            employer=cls.employer1,
            person_month=cls.month4,
            amount=130,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report4,
            calculated_year_result=3 * (100 + 110 + 120 + 130),
        )
        cls.report5 = ASalaryReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month1,
            amount=150,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report5,
            calculated_year_result=12 * 150,
        )
        cls.report6 = ASalaryReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month2,
            amount=120,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report6,
            calculated_year_result=6 * (150 + 120),
        )
        cls.report7 = ASalaryReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month3,
            amount=100,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report7,
            calculated_year_result=4 * (150 + 120 + 100),
        )
        cls.report8 = ASalaryReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month4,
            amount=80,
        )
        CalculationResult.objects.create(
            a_salary_report=cls.report8,
            calculated_year_result=3 * (150 + 120 + 100 + 80),
        )
        cls.report9 = ASalaryReport.objects.create(
            employer=cls.employer2,
            person_month=cls.month5,
            amount=80,
        )
        # No CalculationResult


class TestPerson(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.person), "Jens Hansen")


class TestPersonYear(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.year), "Jens Hansen (2024)")

    def test_salary_reports(self):
        self.assertEqual(
            list(self.year.salary_reports),
            [
                self.report1,
                self.report5,
                self.report2,
                self.report6,
                self.report3,
                self.report7,
                self.report4,
                self.report8,
            ],
        )

    def test_latest_calculation(self):
        self.assertEqual(
            self.year.latest_calculation,
            self.report4.calculated_year_result + self.report8.calculated_year_result,
        )

    def test_no_calculation(self):
        self.assertIsNone(self.report9.calculated_year_result)


class TestPersonMonth(ModelTest):

    def test_shortcuts(self):
        self.assertEqual(self.month1.year, 2024)

    def test_string_methods(self):
        self.assertEqual(str(self.month1), "Jens Hansen (2024/1)")

    def test_calculation(self):
        # Første måned i året
        with patch.object(
            PersonYear, "calculate_benefit", return_value=Decimal("3600")
        ):
            self.month1.calculate_benefit()
            self.month1.save()
            self.assertEqual(self.month1.estimated_year_benefit, Decimal("3600"))
            self.assertEqual(self.month1.prior_benefit_paid, Decimal(0))
            # 3600 / 12
            self.assertEqual(self.month1.benefit_paid, Decimal("300.00"))
        # Anden måned. Samme indkomstgrundlag
        with patch.object(
            PersonYear, "calculate_benefit", return_value=Decimal("3600")
        ):
            self.month2.calculate_benefit()
            self.month2.save()
            self.assertEqual(self.month2.estimated_year_benefit, Decimal("3600"))
            self.assertEqual(self.month2.prior_benefit_paid, Decimal("300.00"))
            # (3600 - 300) / (12 - 1)
            self.assertEqual(self.month2.benefit_paid, Decimal("300.00"))
        # Tredje måned. Højere indkomstgrundlag
        with patch.object(
            PersonYear, "calculate_benefit", return_value=Decimal("4600")
        ):
            self.month3.calculate_benefit()
            self.month3.save()
            self.assertEqual(self.month3.estimated_year_benefit, Decimal("4600"))
            self.assertEqual(self.month3.prior_benefit_paid, Decimal("600.00"))
            # (4600 - 300 - 300) / (12 - 2)
            self.assertEqual(self.month3.benefit_paid, Decimal("400.00"))

    def test_calculation_negative(self):
        # Første måned i året
        with patch.object(
            PersonYear, "calculate_benefit", return_value=Decimal("12000")
        ):
            self.month1.calculate_benefit()
            self.month1.save()
            self.assertEqual(self.month1.estimated_year_benefit, Decimal("12000"))
            self.assertEqual(self.month1.prior_benefit_paid, Decimal(0))
            # 12000 / 12
            self.assertEqual(self.month1.benefit_paid, Decimal("1000.00"))
        # Anden måned. Mindre indkomstgrundlag.
        # Test at vi ikke får negativt beløb ud, men 0
        with patch.object(PersonYear, "calculate_benefit", return_value=Decimal("500")):
            self.month2.calculate_benefit()
            self.month2.save()
            self.assertEqual(self.month2.estimated_year_benefit, Decimal("500"))
            self.assertEqual(self.month2.prior_benefit_paid, Decimal("1000.00"))
            self.assertEqual(self.month2.benefit_paid, Decimal("0.00"))


class TestEmployer(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.employer1), "Fredes Fisk (12345678)")


class TestSalaryReport(ModelTest):

    def test_shortcuts(self):
        self.assertEqual(self.report1.person_year, self.year)
        self.assertEqual(self.report1.person, self.person)
        self.assertEqual(self.report1.year, 2024)
        self.assertEqual(self.report1.month, 1)

    def test_string_methods(self):
        self.assertEqual(
            str(self.report1), "Jens Hansen (2024/1) | Fredes Fisk (12345678)"
        )
