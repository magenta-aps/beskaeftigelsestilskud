# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from common.tests.test_utils import BaseTestCase
from common.utils import get_income_estimates_df, isnan
from django.conf import settings
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import (
    calculate_benefit,
    get_calculation_date,
    get_payout_date,
    get_payout_df,
)
from suila.models import (
    ManagementCommands,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PrismeAccountAlias,
    PrismeBatch,
    PrismeBatchItem,
    StandardWorkBenefitCalculationMethod,
    TaxInformationPeriod,
    Year,
)


class CalculateBenefitTest(BaseTestCase):

    def test_get_income_estimates_df(self):
        df = get_income_estimates_df(12, self.year.year)

        self.assertEqual(len(df.index), 2)
        self.assertIn(self.person1.cpr, df.index)
        self.assertIn(self.person2.cpr, df.index)

        error_person1 = (
            df.loc[self.person1.cpr, "actual_year_result"]
            - df.loc[self.person1.cpr, "estimated_year_result"]
        )

        error_person2 = abs(
            df.loc[self.person2.cpr, "actual_year_result"]
            - df.loc[self.person2.cpr, "estimated_year_result"]
        )

        # Person1 uses InYearExtrapolationEngine, which is good at estimating
        self.assertEqual(error_person1, 0)

        # Person1 uses TwelveMonthsSummationEngine, which is bad at estimating
        self.assertGreater(error_person2, 0)

    def test_get_income_estimates_df_for_person(self):
        df = get_income_estimates_df(12, self.year.year)
        df_person1 = get_income_estimates_df(12, self.year.year, cpr=self.person1.cpr)

        self.assertEqual(len(df_person1.index), 1)

        for col in df.columns:
            self.assertEqual(df.loc[self.person1.cpr, col], df_person1[col].values[0])

    def test_get_income_estimates_df_for_engine(self):
        df = get_income_estimates_df(
            12,
            self.year.year,
            engine_a="TwelveMonthsSummationEngine",
        )
        error_person1 = (
            df.loc[self.person1.cpr, "actual_year_result"]
            - df.loc[self.person1.cpr, "estimated_year_result"]
        )

        error_person2 = abs(
            df.loc[self.person2.cpr, "actual_year_result"]
            - df.loc[self.person2.cpr, "estimated_year_result"]
        )

        # Person1 uses InYearExtrapolationEngine, which is good at estimating
        # But income-estimates for TwelveMonthsSummationEngine are used for this
        # dataframe
        self.assertGreater(error_person1, 0)

        # Person1 uses TwelveMonthsSummationEngine, which is bad at estimating
        self.assertGreater(error_person2, 0)

    def test_get_payout_df(self):
        df = get_payout_df(3, self.year.year)

        self.assertEqual(len(df.index), 2)
        self.assertIn(self.person1.cpr, df.index)
        self.assertIn(self.person2.cpr, df.index)

        self.assertEqual(df.loc[self.person1.cpr, "benefit_transferred_month_1"], 1050)
        self.assertEqual(df.loc[self.person1.cpr, "benefit_transferred_month_2"], 1050)
        self.assertEqual(df.loc[self.person2.cpr, "benefit_transferred_month_1"], 1050)
        self.assertEqual(df.loc[self.person2.cpr, "benefit_transferred_month_2"], 1050)

        self.assertIn("benefit_transferred_month_0", df.columns)
        self.assertIn("benefit_transferred_month_1", df.columns)
        self.assertIn("benefit_transferred_month_2", df.columns)
        self.assertEqual(len(df.columns), 3)

    def test_get_payout_df_for_person(self):
        df = get_payout_df(3, self.year.year)
        df_person1 = get_payout_df(3, self.year.year, cpr=self.person1.cpr)

        self.assertEqual(len(df_person1.index), 1)

        for col in df.columns:
            self.assertEqual(
                df.loc[self.person1.cpr, col],
                df_person1[col].values[0],
            )

    def test_get_empty_payout_df(self):
        df = get_payout_df(1, 1991)
        self.assertTrue(df.empty)

    @override_settings(CALCULATION_SAFETY_FACTOR=1)
    @override_settings(ENFORCE_QUARANTINE=False)
    def test_calculate_benefit(self):
        yearly_salary = 10000 * 12 + 15000 * 12
        correct_benefit = self.year.calculation_method.calculate(yearly_salary) / 12

        for month in range(1, 13):
            df = calculate_benefit(month, self.year.year)
            self.assertEqual(
                df.loc[self.person1.cpr, "benefit_calculated"], correct_benefit
            )

    def test_calculate_benefit_with_safety_factor(self):
        safety_factor = settings.CALCULATION_SAFETY_FACTOR  # type: ignore
        yearly_salary = 10000 * 12 + 15000 * 12
        correct_benefit = self.year.calculation_method.calculate(yearly_salary) / 12

        # The safety factor is applied in January
        df = calculate_benefit(1, self.year.year)
        self.assertEqual(
            df.loc[self.person1.cpr, "benefit_calculated"],
            correct_benefit * safety_factor,
        )

        # But not in December
        df = calculate_benefit(12, self.year.year)
        self.assertEqual(
            df.loc[self.person1.cpr, "benefit_calculated"], correct_benefit
        )

    @patch("common.utils.get_people_in_quarantine")
    def test_calculate_benefit_quarantine_default_settings(
        self, get_people_in_quarantine: MagicMock
    ):
        """
        Bekræft, at der er 10 måneders udbetalingspause med de nuværende karantæne
        settings. Således at der udbetales i januar, baseret på beregningen for
        november.

        https://redmine.magenta.dk/issues/64313
        """

        get_people_in_quarantine.return_value = pd.DataFrame(
            [[True, "foo"], [True, "bar"]],
            index=[self.person1.cpr, self.person2.cpr],
            columns=["in_quarantine", "quarantine_reason"],
        )

        for month in range(1, 13):
            df = calculate_benefit(month, self.year.year)
            benefit_calculated = df.loc[self.person1.cpr, "benefit_calculated"]

            if month <= 10:
                self.assertEqual(benefit_calculated, 0)
            else:
                self.assertGreater(benefit_calculated, 0)

    @patch("common.utils.get_people_in_quarantine")
    def test_calculate_benefit_quarantine(self, get_people_in_quarantine: MagicMock):

        get_people_in_quarantine.return_value = pd.DataFrame(
            [[True, "foo"], [False, "bar"]],
            index=[self.person1.cpr, self.person2.cpr],
            columns=["in_quarantine", "quarantine_reason"],
        )
        yearly_salary = 10000 * 12 + 15000 * 12
        correct_year_benefit = self.year.calculation_method.calculate(yearly_salary)
        quarantine_weights = (
            (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 1, 1),
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 12),
            (0, 0, 0, 0, 0, 12, 0, 0, 0, 0, 0, 0),
            (2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0),
        )

        for weight_list in quarantine_weights:
            with self.settings(QUARANTINE_WEIGHTS=weight_list):

                for month in range(1, 13):
                    correct_month_benefit = (
                        correct_year_benefit * weight_list[month - 1] / 12
                    )

                    df = calculate_benefit(month, self.year.year)
                    get_people_in_quarantine.assert_called()
                    benefit_calculated = df.loc[self.person1.cpr, "benefit_calculated"]
                    self.assertEqual(
                        benefit_calculated,
                        correct_month_benefit,
                        f"For month {month} and weights {weight_list}",
                    )

                    person_month = PersonMonth.objects.get(
                        person_year__person__cpr=self.person1.cpr,
                        month=month,
                        person_year__year__year=self.year.year,
                    )
                    person_month.benefit_transferred = benefit_calculated
                    person_month.save()

    def test_calculate_benefit_pause(self):
        yearly_salary = 10000 * 12 + 15000 * 12
        correct_year_benefit = self.year.calculation_method.calculate(yearly_salary)

        person_year = PersonYear.objects.get(person=self.person1, year=self.year.year)

        test_cases = [
            # person1 is never paused.
            {
                "pause_month": None,
                "unpause_month": None,
            },
            # person1 is paused in January and remains paused for the rest of the year.
            {
                "pause_month": 1,
                "unpause_month": None,
            },
            # person1 is paused in June and remains paused for the rest of the year.
            {
                "pause_month": 6,
                "unpause_month": None,
            },
            # person1 is paused in June and unpaused in august.
            {
                "pause_month": 6,
                "unpause_month": 8,
            },
        ]

        for test_case in test_cases:

            # Reset person1s "pause" attribute for each test case
            person_year.person.paused = False
            person_year.person.save()
            self.assertFalse(person_year.person.paused)

            remaining_year_benefit = correct_year_benefit
            for month in range(1, 13):
                months_remaining = 13 - month

                # Pause all payouts for person1
                if month == test_case["pause_month"]:
                    person_year.person.paused = True
                    person_year.person.save()
                    self.assertTrue(person_year.person.paused)

                # Resume payouts for person1
                if month == test_case["unpause_month"]:
                    person_year.person.paused = False
                    person_year.person.save()
                    self.assertFalse(person_year.person.paused)

                if person_year.person.paused:
                    correct_month_benefit = 0
                else:
                    correct_month_benefit = remaining_year_benefit / months_remaining

                benefit_calculated = calculate_benefit(month, self.year.year).loc[
                    self.person1.cpr,
                    "benefit_calculated",
                ]

                self.assertEqual(benefit_calculated, correct_month_benefit)
                remaining_year_benefit -= Decimal(benefit_calculated)

                person_month = PersonMonth.objects.get(
                    person_year__person__cpr=self.person1.cpr,
                    month=month,
                    person_year__year__year=self.year.year,
                )
                person_month.benefit_transferred = benefit_calculated
                person_month.save()

    def test_isnan(self):
        self.assertTrue(isnan(np.float64(None)))
        self.assertFalse(isnan(np.float64(42)))

    def test_get_payout_date(self):
        self.assertEqual(get_payout_date(2024, 11), date(2024, 11, 19))
        self.assertEqual(get_payout_date(2024, 12), date(2024, 12, 17))
        self.assertEqual(get_payout_date(2025, 1), date(2025, 1, 21))
        self.assertEqual(get_payout_date(2025, 2), date(2025, 2, 18))
        self.assertEqual(get_payout_date(2025, 3), date(2025, 3, 18))
        self.assertEqual(get_payout_date(2025, 4), date(2025, 4, 15))
        self.assertEqual(get_payout_date(2025, 5), date(2025, 5, 20))
        self.assertEqual(get_payout_date(2025, 6), date(2025, 6, 17))
        self.assertEqual(get_payout_date(2025, 7), date(2025, 7, 15))
        self.assertEqual(get_payout_date(2025, 8), date(2025, 8, 19))
        self.assertEqual(get_payout_date(2025, 9), date(2025, 9, 16))
        self.assertEqual(get_payout_date(2025, 10), date(2025, 10, 21))
        self.assertEqual(get_payout_date(2025, 11), date(2025, 11, 18))
        self.assertEqual(get_payout_date(2025, 12), date(2025, 12, 16))

    def test_get_calculation_date(self):
        self.assertEqual(get_calculation_date(2024, 11), date(2024, 11, 8))
        self.assertEqual(get_calculation_date(2024, 12), date(2024, 12, 6))
        self.assertEqual(get_calculation_date(2025, 1), date(2025, 1, 10))
        self.assertEqual(get_calculation_date(2025, 2), date(2025, 2, 7))
        self.assertEqual(get_calculation_date(2025, 3), date(2025, 3, 7))
        self.assertEqual(get_calculation_date(2025, 4), date(2025, 4, 4))
        self.assertEqual(get_calculation_date(2025, 5), date(2025, 5, 9))
        self.assertEqual(get_calculation_date(2025, 6), date(2025, 6, 6))
        self.assertEqual(get_calculation_date(2025, 7), date(2025, 7, 4))
        self.assertEqual(get_calculation_date(2025, 8), date(2025, 8, 8))
        self.assertEqual(get_calculation_date(2025, 9), date(2025, 9, 5))
        self.assertEqual(get_calculation_date(2025, 10), date(2025, 10, 10))
        self.assertEqual(get_calculation_date(2025, 11), date(2025, 11, 7))
        self.assertEqual(get_calculation_date(2025, 12), date(2025, 12, 5))

    def test_benefit_calculated_ceil_rounding(self):
        df = calculate_benefit(1, self.year.year)

        # Assert the DataFrame "benefit_calculated"-series have been rounded up
        # OBS: if not, the value "1056.0" will be "1055.61"
        pd.testing.assert_series_equal(
            df["benefit_calculated"].astype(pd.Float64Dtype()),
            pd.Series(
                [1050.0, 1056.0],
                name="benefit_calculated",
                dtype=pd.Float64Dtype(),
                index=pd.Index(["1234567890", "1234567891"], dtype="object"),
            ),
        )

    def assert_management_command(self, months, **kwargs):
        for month in months:
            month.benefit_calculated = 0
            month.save()

        self.assertGreater(len(months), 0)
        self.assertEqual(sum([month.benefit_calculated for month in months]), 0)
        for month in months:
            self.call_command(
                "calculate_benefit", self.year.year, month.month, **kwargs
            )
        for month in months:
            month.refresh_from_db()

        self.assertGreater(sum([month.benefit_calculated for month in months]), 0)

    def test_management_command(self):
        months = PersonMonth.objects.filter(person_year__year=self.year)
        self.assert_management_command(months)

    def test_management_command_for_months_with_prisme_items(self):
        months = PersonMonth.objects.filter(person_year__year=self.year)

        prisme_batch = PrismeBatch.objects.create(
            status="sent", export_date=date.today(), prefix=1
        )

        for month in months:
            PrismeBatchItem.objects.create(
                person_month=month, prisme_batch=prisme_batch
            )
            month.benefit_calculated = 0
            month.save()

        for month in months:
            self.call_command("calculate_benefit", self.year.year, month.month)
            month.refresh_from_db()

        self.assertEqual(sum([month.benefit_calculated for month in months]), 0)

    def test_management_command_for_single_month(self):
        months = PersonMonth.objects.filter(person_year__year=self.year, month=2)
        self.assert_management_command(months)

    def test_management_command_for_single_cpr(self):
        months = PersonMonth.objects.filter(
            person_year__year=self.year, month=2, person_year__person__cpr="1234567890"
        )
        self.assert_management_command(months, cpr="1234567890")

    @patch("suila.management.commands.calculate_benefit.isnan", return_value=True)
    def test_management_command_for_nan_values(self, isnan):
        for month in PersonMonth.objects.filter(person_year__year=self.year):
            self.call_command("calculate_benefit", self.year.year, month.month)
            month.refresh_from_db()
            self.assertIsNone(month.benefit_calculated)

    def test_management_command_verbose(self):
        stdout, _ = self.call_command(
            "calculate_benefit", self.year.year, 1, verbosity=2
        )
        self.assertIn("Calculating benefit", stdout.getvalue())

    @patch("suila.management.commands.common.Profile")
    def test_management_command_profile(self, profiler):
        self.call_command("calculate_benefit", self.year.year, 1, profile=True)
        self.assertTrue(profiler.called)

    @patch("suila.management.commands.calculate_benefit.calculate_benefit")
    @patch("suila.management.commands.common.CommandError")
    def test_management_command_reraise(self, command_error, calculate_benefit):
        calculate_benefit.side_effect = Exception("foo")
        command_error.return_value = Exception("bar")

        with self.assertRaisesMessage(Exception, "bar"):
            self.call_command("calculate_benefit", self.year.year, 1, reraise=False)

        with self.assertRaisesMessage(Exception, "foo"):
            self.call_command("calculate_benefit", self.year.year, 1, reraise=True)


class IntegrationBaseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
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

    def make_person_and_person_year(self, name, cpr, engine):

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
        We allow a margin of +/- 5 kr to allow for rounding (We always round to the
        nearest krone when paying out)
        """

        self.assertGreater(benefit_calculated, correct_benefit - 5)
        self.assertLess(benefit_calculated, correct_benefit + 5)


class CalculateBenefitTaxScopeTest(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(
            cls,
            "Borger som skal have Suila-tapit, dukker op fra 1. juli",
            cls.cpr,
            "MonthlyContinuationEngine",
        )

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

            kwargs = {
                "person_year__person__cpr": self.cpr,
                "month": month,
                "person_year__year__year": self.year.year,
            }

            if month >= 7:
                person_month = PersonMonth.objects.get(**kwargs)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 1312)
            else:
                person_months = PersonMonth.objects.filter(**kwargs)
                self.assertEqual(person_months.count(), 0)

        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], 1312 * 6)

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

        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], 1312 * 6)


class CalculateBenefitTaxScopeTest2(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567893"
        cls.person, cls.person_year = cls.make_person_and_person_year(
            cls,
            "Borger skal ikke have suila-tapit, dukker op 1. september",
            cls.cpr,
            "MonthlyContinuationEngine",
        )

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

        Borgeren får kr. 50.000 om måneden, svarende til en årsindkomst på 600.000
        kroner.

        Vi har

        E = 200.000
        B = 200.000 * (12 / 4) = 600.000

        Vedkommende får derfor ingen suila-tapit.
        """

        for month in range(1, 13):
            self.call_commands(month)

            kwargs = {
                "person_year__person__cpr": self.cpr,
                "month": month,
                "person_year__year__year": self.year.year,
            }

            if month >= 9:
                person_month = PersonMonth.objects.get(**kwargs)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 200_000)
                self.assert_benefit(benefit_calculated, 0)
            else:
                person_months = PersonMonth.objects.filter(**kwargs)
                self.assertEqual(person_months.count(), 0)

        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], 0)


class CalculateBenefitTaxScopeTest3(IntegrationBaseTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.cpr = "1234567892"
        cls.person, cls.person_year = cls.make_person_and_person_year(
            cls,
            "Borger som skal have Suila-tapit, skattepligtig fra juli-september",
            cls.cpr,
            "MonthlyContinuationEngine",
        )

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

            kwargs = {
                "person_year__person__cpr": self.cpr,
                "month": month,
                "person_year__year__year": self.year.year,
            }

            if month >= 7 and month <= 9:
                person_month = PersonMonth.objects.get(**kwargs)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 1312)
            else:
                person_months = PersonMonth.objects.filter(**kwargs)
                self.assertEqual(person_months.count(), 0)

        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], 1312 * 3)

    def test_estimate_and_calculate_benefit_no_tax_period(self):
        """
        If the person is not taxable we do not payout (But we still estimate!)
        """
        TaxInformationPeriod.objects.all().delete()

        for month in range(1, 13):
            self.call_commands(month)

            kwargs = {
                "person_year__person__cpr": self.cpr,
                "month": month,
                "person_year__year__year": self.year.year,
            }

            if month >= 7 and month <= 9:
                person_month = PersonMonth.objects.get(**kwargs)
                benefit_calculated = person_month.benefit_calculated
                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(benefit_calculated, 0)
            else:
                person_months = PersonMonth.objects.filter(**kwargs)
                self.assertEqual(person_months.count(), 0)

        total = PersonMonth.objects.aggregate(
            total_transferred=Sum("benefit_transferred")
        )
        self.assert_benefit(total["total_transferred"], 0)
