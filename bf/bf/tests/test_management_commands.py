# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from io import StringIO
from unittest import mock

import pandas as pd
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings

from bf.models import Person, PersonMonth, PersonYear, Year


@mock.patch("common.utils.calculate_benefit")
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

        cls.person_months = [
            PersonMonth.objects.create(
                month=month,
                person_year=cls.person_year_2022,
                import_date="2022-01-01",
                actual_year_benefit=1200,
            )
            for month in range(1, 13)
        ]

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "autoselect_estimation_engine",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )

    def test_autoselect(self, calculate_benefit):
        # By default the engines for 2023 equal the default engine
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_a,
            "InYearExtrapolationEngine",
        )
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_b,
            "InYearExtrapolationEngine",
        )

        # But in 2022 TwelveMonthsSummationEngine was better (for A income)
        # And for B income the InYearExtrapolationEngine was best
        #
        # We simulate this by making all OTHER engines return zero-results.
        def mess_other_engines_up(*args, **kwargs):

            df = pd.DataFrame(index=[self.person.cpr])

            if kwargs["engine_a"] != "TwelveMonthsSummationEngine":
                df["estimated_year_benefit"] = 0
                df["actual_year_benefit"] = 1200
                df["benefit_paid"] = 0
            elif kwargs["engine_b"] != "InYearExtrapolationEngine":
                df["estimated_year_benefit"] = 0
                df["actual_year_benefit"] = 1200
                df["benefit_paid"] = 0
            else:
                df["estimated_year_benefit"] = 1200
                df["actual_year_benefit"] = 1200
                df["benefit_paid"] = 100

            return df

        calculate_benefit.side_effect = mess_other_engines_up

        # Now run the autoselect command
        self.call_command(2023)
        self.person_year_2023.refresh_from_db()

        # See. Now the engines are updated for 2023: To those that were best in 2022
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_a,
            "TwelveMonthsSummationEngine",
        )
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_b,
            "InYearExtrapolationEngine",
        )


@mock.patch("bf.management.commands.job_dispatcher.management")
class MasterJobTest(TestCase):

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "job_dispatcher",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )

    def get_called_management_commands(self, management_mock):
        calls = management_mock.call_command.call_args_list
        return [c.args[0] for c in calls]

    def test_first_jan(self, management):
        self.call_command(year=2024, month=1, day=1)
        called_commands = self.get_called_management_commands(management)

        self.assertIn("calculate_stability_score", called_commands)
        self.assertIn("autoselect_estimation_engine", called_commands)

        management.call_command.assert_any_call(
            "calculate_stability_score", 2023, verbosity=1
        )
        management.call_command.assert_any_call(
            "autoselect_estimation_engine", 2024, verbosity=1
        )

    def test_second_jan(self, management):
        self.call_command(year=2024, month=1, day=2)

        called_commands = self.get_called_management_commands(management)

        self.assertNotIn("calculate_stability_score", called_commands)
        self.assertNotIn("autoselect_estimation_engine", called_commands)

    def test_calculation_date_jan(self, management):
        self.call_command(year=2024, month=1, day=9)  # Second tuesday in january
        management.call_command.assert_any_call(
            "calculate_benefit", 2024, month=1, cpr=None, verbosity=1
        )

    def test_prisme_date_jan(self, management):
        self.call_command(year=2024, month=1, day=15)  # day before third tuesday
        management.call_command.assert_any_call(
            "export_benefits_to_prisme", year=2024, month=1, verbosity=1
        )

    @override_settings(ESKAT_BASE_URL="http://foo")
    def test_load_data_from_eskat(self, management):
        self.call_command(year=2024, month=1, day=1)

        management.call_command.assert_any_call(
            "load_eskat", 2024, "expectedincome", month=None, verbosity=1, cpr=None
        )
        management.call_command.assert_any_call(
            "load_eskat", 2024, "monthlyincome", month=1, verbosity=1, cpr=None
        )
        management.call_command.assert_any_call(
            "load_eskat", 2024, "taxinformation", month=1, verbosity=1, cpr=None
        )

    @override_settings(ESKAT_BASE_URL=None)
    def test_load_data_from_eskat_no_url(self, management):
        self.call_command(year=2024, month=1, day=1)
        called_commands = self.get_called_management_commands(management)

        self.assertNotIn("load_eskat", called_commands)
