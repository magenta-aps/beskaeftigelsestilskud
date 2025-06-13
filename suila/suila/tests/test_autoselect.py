# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from suila.models import IncomeType, Person, PersonYear, PersonYearEstimateSummary, Year


class AutoSelectEngineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year_2022 = Year.objects.create(year=2022)
        cls.year_2023 = Year.objects.create(year=2023)
        cls.person = Person.objects.create(cpr="123")
        cls.person2 = Person.objects.create(cpr="1234")
        cls.person_year_2022 = PersonYear.objects.create(
            year=cls.year_2022, person=cls.person
        )
        cls.person_year_2023 = PersonYear.objects.create(
            year=cls.year_2023, person=cls.person
        )

        cls.person2_year_2022 = PersonYear.objects.create(
            year=cls.year_2022, person=cls.person2
        )
        cls.person2_year_2023 = PersonYear.objects.create(
            year=cls.year_2023, person=cls.person2
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
        call_command(
            "autoselect_estimation_engine",
            *args,
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
        self.call_command(year=2023)

        # See. Now the engines are updated for 2023: To those that were best in 2022
        self.assert_that_engines_are_updated()

    def test_autoselect_cpr_arg(self):
        # Call the command for a different person
        self.call_command(year=2023, cpr="0011")

        # The engine still equals the default engine for person with cpr = 123
        self.assert_that_engines_equal_defaults()

    def test_autoselect_for_all_years(self):
        self.call_command()
        self.assert_that_engines_are_updated()

    def test_autoselect_for_empty_year(self):
        self.call_command(year=2022)
        self.assert_that_engines_equal_defaults()

    def test_autoselect_for_nonexisting_person_year(self):
        qs = PersonYear.objects.filter(year__year=2023)
        qs.delete()

        self.assertEqual(qs.count(), 0)
        self.call_command(year=2023)
        self.assertGreater(qs.count(), 0)

        self.assertEqual(
            qs[0].preferred_estimation_engine_a, "TwelveMonthsSummationEngine"
        )
        self.assertEqual(
            qs[0].preferred_estimation_engine_u, "InYearExtrapolationEngine"
        )

    def test_verbose(self):
        stdout = StringIO()
        self.call_command(verbosity=3, stdout=stdout)
        self.assertIn("Processing person 1", stdout.getvalue())

    def test_no_years_to_process(self):
        # There is no year before 2022. So if we  call with year=2022 there are no
        # years to process
        stdout = StringIO()
        self.call_command(year=2022, verbosity=3, stdout=stdout)
        self.assertIn("No relevant years found", stdout.getvalue())

    def test_no_relevant_summaries(self):
        # Person 1234 has no summaries
        stdout = StringIO()
        self.call_command(year=2023, cpr="1234", stdout=stdout, verbosity=3)
        self.assertIn("No relevant PersonYearEstimateSummaries", stdout.getvalue())
