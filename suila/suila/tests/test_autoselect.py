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
            income_type=IncomeType.B,
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
            income_type=IncomeType.B,
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

    def test_autoselect(self):
        # By default the engines for 2023 equal the default engine
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_a,
            "InYearExtrapolationEngine",
        )
        self.assertEqual(
            self.person_year_2023.preferred_estimation_engine_b,
            "SelfReportedEngine",
        )

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
