# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from common.tests.test_utils import BaseTestCase
from common.utils import get_income_estimates_df, isnan
from django.conf import settings
from django.test import override_settings

from suila.benefit import calculate_benefit, get_payout_date, get_payout_df
from suila.models import PersonMonth


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

        self.assertEqual(df.loc[self.person1.cpr, "benefit_paid_month_1"], 1050)
        self.assertEqual(df.loc[self.person1.cpr, "benefit_paid_month_2"], 1050)
        self.assertEqual(df.loc[self.person2.cpr, "benefit_paid_month_1"], 1050)
        self.assertEqual(df.loc[self.person2.cpr, "benefit_paid_month_2"], 1050)

        self.assertIn("benefit_paid_month_0", df.columns)
        self.assertIn("benefit_paid_month_1", df.columns)
        self.assertIn("benefit_paid_month_2", df.columns)
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
            self.assertEqual(df.loc[self.person1.cpr, "benefit_paid"], correct_benefit)

    def test_calculate_benefit_with_safety_factor(self):
        safety_factor = settings.CALCULATION_SAFETY_FACTOR  # type: ignore
        yearly_salary = 10000 * 12 + 15000 * 12
        correct_benefit = self.year.calculation_method.calculate(yearly_salary) / 12

        # The safety factor is applied in January
        df = calculate_benefit(1, self.year.year)
        self.assertEqual(
            df.loc[self.person1.cpr, "benefit_paid"], correct_benefit * safety_factor
        )

        # But not in December
        df = calculate_benefit(12, self.year.year)
        self.assertEqual(df.loc[self.person1.cpr, "benefit_paid"], correct_benefit)

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
            benefit_paid = df.loc[self.person1.cpr, "benefit_paid"]

            if month <= 10:
                self.assertEqual(benefit_paid, 0)
            else:
                self.assertGreater(benefit_paid, 0)

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
                    benefit_paid = df.loc[self.person1.cpr, "benefit_paid"]
                    self.assertEqual(
                        benefit_paid,
                        correct_month_benefit,
                        f"For month {month} and weights {weight_list}",
                    )

                    person_month = PersonMonth.objects.get(
                        person_year__person__cpr=self.person1.cpr,
                        month=month,
                        person_year__year__year=self.year.year,
                    )
                    person_month.benefit_paid = benefit_paid
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

    def test_benefit_paid_ceil_rounding(self):
        df = calculate_benefit(1, self.year.year)

        # Assert the DataFrame "benefit_paid"-series have been rounded up
        # OBS: if not, the value "1056.0" will be "1055.61"
        pd.testing.assert_series_equal(
            df["benefit_paid"].astype(pd.Float64Dtype()),
            pd.Series(
                [1050.0, 1056.0],
                name="benefit_paid",
                dtype=pd.Float64Dtype(),
                index=pd.Index(["1234567890", "1234567891"], dtype="object"),
            ),
        )
