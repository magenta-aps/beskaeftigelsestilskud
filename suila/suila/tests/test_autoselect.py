# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from suila.models import IncomeType, Person, PersonYear, PersonYearEstimateSummary, Year


class AutoSelectEngineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year_2022 = Year.objects.create(year=2022)
        cls.year_2023 = Year.objects.create(year=2023)
        cls.person = Person.objects.create(cpr="123")
        cls.person_year_2022 = PersonYear.objects.create(
            year=cls.year_2022, person=cls.person
        )
        cls.person_year_2023 = PersonYear.objects.create(
            year=cls.year_2023, person=cls.person
        )
        PersonYearEstimateSummary.objects.create(
            person_year=cls.person_year_2022,
            estimation_engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
            mean_error_percent=Decimal(100),
            rmse_percent=Decimal(50),
        )
        PersonYearEstimateSummary.objects.create(
            person_year=cls.person_year_2022,
            estimation_engine="InYearExtrapolationEngine",
            income_type=IncomeType.U,
            mean_error_percent=Decimal(100),
            rmse_percent=Decimal(50),
        )
        PersonYearEstimateSummary.objects.create(
            person_year=cls.person_year_2022,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.A,
            mean_error_percent=Decimal(10),
            rmse_percent=Decimal(10),
        )
        PersonYearEstimateSummary.objects.create(
            person_year=cls.person_year_2022,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.U,
            mean_error_percent=Decimal(200),
            rmse_percent=Decimal(60),
        )

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "autoselect_estimation_engine",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )

    def assert_that_engines_equal_defaults(self):
        # Check that engines equal their default values
        self.person_year_2023.refresh_from_db()
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_a,
            "InYearExtrapolationEngine",
        )
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_u,
            "TwelveMonthsSummationEngine",
        )

    def assert_that_engines_are_updated(self):
        # Check that the engines are updated for 2023: To those that were best in 2022
        self.person_year_2023.refresh_from_db()
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_a,
            "TwelveMonthsSummationEngine",
        )
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_u,
            "InYearExtrapolationEngine",
        )

    def test_autoselect(self):
        # By default the engines for 2023 equal the default engine
        self.assert_that_engines_equal_defaults()

        # Now run the autoselect command
        self.call_command(2023)

        # See. Now the engines are updated for 2023: To those that were best in 2022
        self.assert_that_engines_are_updated()

    def test_autoselect_cpr_arg(self):
        # Call the command for a different person
        self.call_command(2023, cpr="0011")

        # The engine still equals the default engine for person with cpr = 123
        self.assert_that_engines_equal_defaults()

    def test_autoselect_for_all_years(self):
        self.call_command(0)
        self.assert_that_engines_are_updated()

    def test_autoselect_for_empty_year(self):
        self.call_command(2022)
        self.assert_that_engines_equal_defaults()

    @patch("suila.management.commands.autoselect_estimation_engine.PersonYear.objects")
    def test_autoselect_for_nonexising_person_year(self, person_year_mock):
        person_year_mock.get.side_effect = PersonYear.DoesNotExist
        self.call_command(2023)
        self.assert_that_engines_equal_defaults()

    @patch("suila.management.commands.autoselect_estimation_engine.Profile")
    def test_autoselect_management_command_profiler(self, profiler):
        self.assertFalse(profiler.called)
        self.call_command(2023, profile=True)
        self.assertTrue(profiler.called)
