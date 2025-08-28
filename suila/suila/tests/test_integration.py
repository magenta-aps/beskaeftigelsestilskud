# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from suila.models import (
    ManagementCommands,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PrismeAccountAlias,
    StandardWorkBenefitCalculationMethod,
    TaxInformationPeriod,
    Year,
)


class IntegrationBaseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("60000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )

        cls.year = Year.objects.create(year=2024, calculation_method=cls.calc)

        cls.prisme_patcher = patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        )

        cls.prisme_mock = cls.prisme_patcher.start()
        cls.location_code = "A5"

        PrismeAccountAlias.objects.create(
            alias="123",
            tax_municipality_location_code=cls.location_code,
            tax_year=cls.year.year,
        )

        cls.stdout = StringIO()

    def make_person_and_person_year(self, cpr, engine="MonthlyContinuationEngine"):

        person = Person.objects.create(
            name="Borger som skal have Suila-tapit, dukker op fra 1. juli",
            cpr=cpr,
            location_code=self.location_code,
        )

        person_year = PersonYear.objects.create(
            person=person,
            year=self.year,
            preferred_estimation_engine_a=engine,
        )
        return person, person_year

    @classmethod
    def _get_datetime(self, month: int, day: int):
        return datetime(
            self.year.year, month, day, tzinfo=timezone.get_current_timezone()
        )

    def call_commands(self, month):
        """
        Runs estimate, calculate, export commands to simulate a full calculation flow:
            - ESTIMATE INCOME estimated a persons income
            - CALCULATE_BENEFIT uses that income to determine the benefit
            - EXPORT_BENEFITS_TO_PRISME locks benefits by populating benefit_transferred
        """
        call_command(
            ManagementCommands.ESTIMATE_INCOME,
            year=self.year.year,
            stdout=self.stdout,
        )
        call_command(
            ManagementCommands.CALCULATE_BENEFIT,
            self.year.year,
            month,
            stdout=self.stdout,
        )
        call_command(
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
            year=self.year.year,
            month=month,
            stdout=self.stdout,
        )

    def assert_benefit(self, benefit_calculated, correct_benefit):
        """
        Compare calculated benefit to expected benefit

        Notes
        -------
        We allow a margin of +/- 12 kr to allow for rounding (We always round to the
        nearest krone when paying out)

        The margin is 12 because a rounding error every month of 1kr gives
        a 12 kr difference in December.
        """

        self.assertGreater(benefit_calculated, correct_benefit - 12)
        self.assertLess(benefit_calculated, correct_benefit + 12)

    def get_person_month(self, month):

        return PersonMonth.objects.get(
            person_year__person__cpr=self.cpr,
            month=month,
            person_year__year__year=self.year.year,
        )

    def assert_total_benefit(self, amount):
        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], amount)


class SteadyAverageIncomeTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(20000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated
            self.assertEqual(person_month.estimated_year_result, 240_000)
            self.assert_benefit(benefit_calculated, 1312)

        self.assert_total_benefit(15_750)


class SteadyHighIncomeTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(30000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated
            self.assertEqual(person_month.estimated_year_result, 360_000)
            self.assert_benefit(benefit_calculated, 735)

        self.assert_total_benefit(8_820)


class SteadyLowIncomeTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(8000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated
            self.assertEqual(person_month.estimated_year_result, 96_000)
            self.assert_benefit(benefit_calculated, 379)

        self.assert_total_benefit(4_550)


class LowIncomeUntilJulyTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(8000) if month_number < 7 else Decimal(0),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated

            if month < 7:
                self.assertEqual(person_month.estimated_year_result, 96_000)
                self.assert_benefit(benefit_calculated, 379)
            else:
                self.assertLess(person_month.estimated_year_result, 96_000)
                self.assertLess(person_month.benefit_calculated, 379)

        self.assert_total_benefit(2_280)


class LowIncomeFromJulyTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(8000) if month_number >= 7 else Decimal(0),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated

            if month >= 7:
                self.assertEqual(person_month.estimated_year_result, 48_000)
            else:
                self.assertEqual(person_month.estimated_year_result, 0)
            self.assert_benefit(benefit_calculated, 0)

        self.assert_total_benefit(0)


class IncomeSpikeInJulyTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(1, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(500_000) if month_number == 7 else Decimal(8000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(1, 1),  # 1. January
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            benefit_calculated = person_month.benefit_calculated

            if month >= 7:
                self.assert_benefit(benefit_calculated, 0)
            else:
                self.assert_benefit(benefit_calculated, 379)

        self.assert_total_benefit(379 * 6)


class CalculateBenefitTaxScopeTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(7, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(20000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(7, 1),  # 1. July
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        """
        Test example 1 from https://redmine.magenta.dk/issues/65645#note-4:

        Eksempel: Borger skal have Suila-tapit, dukker op fra 1. juli

        Personen tjener 20.000 kroner pr. måned svarende til en årsindkomst på 240.000
        kroner og kommer til at tjene 120.000 som fuldt skattepligtig.

        Fra 1. juli har vi

        E = 6*20.000 = 120.000
        B = 120.000* (12/6) = 240.000

        Vedkommende vil derfor få 1312 kr. pr. måned i 6 måneder = 7872 kroner i alt.
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7:
                person_month = self.get_person_month(month)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 1312)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(1312 * 6)

    def test_estimate_and_calculate_benefit_default_engine(self):
        """
        Engine = InYearExtrapolationEngine is not so good at estimating annual income
        for people who are new to the job-market. Therefore the monthly amount that we
        pay out will not be nicely 1312 kr. every month.

        But the final transferred amount should still be the same (1312 * 6)
        """
        self.person_year.preferred_estimation_engine_a = "InYearExtrapolationEngine"
        self.person_year.save()

        for month in range(1, 13):
            self.call_commands(month)

        self.assert_total_benefit(1312 * 6)


class CalculateBenefitTaxScopeTest2(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567893"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(9, 13):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(50_000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(9, 1),  # 1. September
            end_date=cls._get_datetime(12, 31),  # 31. December
        )

    def test_estimate_and_calculate_benefit(self):
        """
        Test example 2 from https://redmine.magenta.dk/issues/65645#note-4:

        Eksempel: Borger skal ikke have suila-tapit, dukker op 1. september

        Borgeren får kr. 50.000 om måneden, svarende til en årsindkomst på 600.000
        kroner.

        Vi har

        E = 200.000
        B = 200.000 * (12 / 4) = 600.000

        Vedkommende får derfor ingen suila-tapit.
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 9:
                person_month = self.get_person_month(month)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 200_000)
                self.assert_benefit(benefit_calculated, 0)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(0)


class CalculateBenefitTaxScopeTest3(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(cls, cls.cpr)

        for month_number in range(7, 10):
            month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month_number,
                import_date=date.today(),
            )
            MonthlyIncomeReport.objects.create(
                person_month=month,
                salary_income=Decimal(20000),
                month=month.month,
                year=cls.year.year,
            )

        TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(7, 1),  # 1. July
            end_date=cls._get_datetime(9, 30),  # 30. September
        )

    def test_estimate_and_calculate_benefit(self):
        """
        We cannot know in advance if a citizen will disappear in the course of a year
        Therefore we payout normally untill the citizen actually disappers. When the
        citizen has disappeared we do not payout
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7 and month <= 9:
                person_month = self.get_person_month(month)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 1312)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(1312 * 3)

    def test_estimate_and_calculate_benefit_no_tax_period(self):
        """
        If the person is not taxable we do not payout (But we still estimate!)
        """
        TaxInformationPeriod.objects.all().delete()

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7 and month <= 9:
                person_month = self.get_person_month(month)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 0)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(0)
