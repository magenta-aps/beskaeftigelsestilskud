# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from io import StringIO
from unittest import mock

import pandas as pd
from django.core.management import call_command
from django.test import TestCase

from suila.models import Person, PersonMonth, PersonYear, Year


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
