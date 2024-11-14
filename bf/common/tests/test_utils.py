# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from itertools import cycle
from unittest import mock

import numpy as np
import pandas as pd
from common.utils import (
    add_parameters_to_url,
    calculate_benefit,
    calculate_stability_score,
    calculate_stability_score_for_entire_year,
    camelcase_to_snakecase,
    get_income_as_dataframe,
    get_income_estimates_df,
    get_payout_date,
    get_payout_df,
    get_people_in_quarantine,
    isnan,
    map_between_zero_and_one,
    to_dataframe,
)
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings

from bf.models import (
    Employer,
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


class TestUtils(TestCase):
    def test_add_parameters_to_url(self):
        url = "http://foo.com"
        parameters_to_add = {"mucki": 1, "bar": "test"}

        url_with_parameters = add_parameters_to_url(url, parameters_to_add)
        self.assertEqual(url_with_parameters, "http://foo.com?mucki=1&bar=test")

    def test_camelcase_to_snakecase(self):
        self.assertEqual(camelcase_to_snakecase("hepHey"), "hep_hey")
        self.assertEqual(camelcase_to_snakecase("hepHeyGL"), "hep_hey_gl")
        self.assertEqual(camelcase_to_snakecase("hepHeyGLFoobar"), "hep_hey_gl_foobar")
        self.assertEqual(
            camelcase_to_snakecase("hepHeyGLFoobar42"), "hep_hey_gl_foobar42"
        )


class TestStabilityScoreUtils(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.unstable_income = [0, 200, 300, 200, 10, 20000]
        cls.stable_income = [200, 200, 200, 201]
        cls.reasonably_stable_income = [35511, 35511, 35511, 35511, 35511, 35511, 74436]

        cls.year = Year.objects.create(year=2022)
        cls.person = Person.objects.create(cpr="0101011234")
        cls.person_year = PersonYear.objects.create(year=cls.year, person=cls.person)

        cls.employer = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )

        cls.person_months = []
        for month in range(1, 13):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year,
                month=month,
                import_date="2022-01-01",
            )
            cls.person_months.append(person_month)

        for counter, amount in enumerate(cls.unstable_income):
            MonthlyBIncomeReport.objects.create(
                amount=amount,
                trader=cls.employer,
                person_month=cls.person_months[counter],
            )
        for counter, amount in enumerate(cls.reasonably_stable_income):
            MonthlyAIncomeReport.objects.create(
                salary_income=amount,
                employer=cls.employer,
                person_month=cls.person_months[counter],
            )

    def test_map_between_zero_and_one(self):
        self.assertEqual(map_between_zero_and_one(0), 1)
        self.assertEqual(map_between_zero_and_one(1000), 0)
        self.assertGreater(map_between_zero_and_one(0.3), 0)
        self.assertLess(map_between_zero_and_one(0.3), 1)

    def test_calculate_stability_score(self):
        self.assertLess(calculate_stability_score(self.unstable_income), 0.01)
        self.assertGreater(calculate_stability_score(self.stable_income), 0.99)

        self.assertGreater(
            calculate_stability_score(self.reasonably_stable_income), 0.2
        )
        self.assertLess(calculate_stability_score(self.reasonably_stable_income), 0.8)
        self.assertEqual(calculate_stability_score([0, 0, 0, 0]), 1)

    def test_to_dataframe(self):
        qs = MonthlyAIncomeReport.objects.all().order_by("month")
        df = to_dataframe(qs, "person__cpr", {"amount": float})
        self.assertIn(self.person.cpr, df.index)
        self.assertEqual(list(df["amount"].values), self.reasonably_stable_income)

    def test_get_income_as_dataframe(self):
        income_dict = get_income_as_dataframe(self.year.year)

        df_a = income_dict["A"]
        df_b = income_dict["B"]

        self.assertIn(self.person.cpr, df_a.index)
        self.assertIn(self.person.cpr, df_b.index)

        for month_counter, amount in enumerate(self.reasonably_stable_income):
            month = month_counter + 1
            self.assertEqual(amount, df_a.loc[self.person.cpr, month])

        for month_counter, amount in enumerate(self.unstable_income):
            month = month_counter + 1
            self.assertEqual(amount, df_b.loc[self.person.cpr, month])

    def test_calculate_stability_score_for_entire_year(self):
        df = calculate_stability_score_for_entire_year(self.year.year)

        # A income is reasonably stable
        self.assertLess(df.loc[self.person.cpr, "A"], 0.8)
        self.assertGreater(df.loc[self.person.cpr, "A"], 0.2)

        # B income is unstable
        self.assertLess(df.loc[self.person.cpr, "B"], 0.2)


class BaseTestCase(TestCase):
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
        cls.last_year = Year.objects.create(year=2023, calculation_method=cls.calc)
        cls.person1 = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person2 = Person.objects.create(
            name="Jens Jansen",
            cpr="1234567891",
        )
        person_years = []
        for year in [cls.last_year, cls.year]:
            person_year1 = PersonYear.objects.create(
                person=cls.person1,
                year=year,
                preferred_estimation_engine_a="InYearExtrapolationEngine",
                preferred_estimation_engine_b="InYearExtrapolationEngine",
            )

            person_year2 = PersonYear.objects.create(
                person=cls.person2,
                year=year,
                preferred_estimation_engine_a="TwelveMonthsSummationEngine",
                preferred_estimation_engine_b="TwelveMonthsSummationEngine",
            )
            person_years.append(person_year1)
            person_years.append(person_year2)

        cls.employer = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )

        for person_year in person_years:
            for month_number in range(1, 13):
                month = PersonMonth.objects.create(
                    person_year=person_year,
                    month=month_number,
                    import_date=date.today(),
                    benefit_paid=1050,
                    prior_benefit_paid=1050 * (month_number - 1),
                    actual_year_benefit=1050 * 12,
                )
                a_income = MonthlyAIncomeReport.objects.create(
                    employer=cls.employer,
                    person_month=month,
                    salary_income=Decimal(10000),
                    month=month.month,
                    year=cls.year.year,
                    person=person_year.person,
                )
                b_income = MonthlyBIncomeReport.objects.create(
                    trader=cls.employer,
                    person_month=month,
                    amount=Decimal(15000),
                    month=month.month,
                    year=cls.year.year,
                    person=person_year.person,
                )

                # The InYearExtrapolationEngine estimates correctly
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * a_income.amount,
                    actual_year_result=month_number * a_income.amount,
                    engine="InYearExtrapolationEngine",
                    income_type=IncomeType.A,
                )
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * b_income.amount,
                    actual_year_result=month_number * b_income.amount,
                    engine="InYearExtrapolationEngine",
                    income_type=IncomeType.B,
                )

                # The TwelveMonthsSummationEngine does not estimate correctly
                # (At least in this dummy-data)
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * 9911,
                    actual_year_result=month_number * a_income.amount,
                    engine="TwelveMonthsSummationEngine",
                    income_type=IncomeType.A,
                )
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * 5522,
                    actual_year_result=month_number * b_income.amount,
                    engine="TwelveMonthsSummationEngine",
                    income_type=IncomeType.B,
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
            engine_b="TwelveMonthsSummationEngine",
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

    @mock.patch("common.utils.get_people_in_quarantine")
    def test_calculate_benefit_quarantine(self, get_people_in_quarantine):

        get_people_in_quarantine.return_value = pd.DataFrame(
            [[True, "foo"], [False, "bar"]],
            index=[self.person1.cpr, self.person2.cpr],
            columns=["in_quarantine", "quarantine_reason"],
        )
        yearly_salary = 10000 * 12 + 15000 * 12

        for month in range(1, 13):

            if month == 12:
                correct_benefit = self.year.calculation_method.calculate(yearly_salary)
            else:
                correct_benefit = 0

            df = calculate_benefit(month, self.year.year)
            self.assertEqual(df.loc[self.person1.cpr, "benefit_paid"], correct_benefit)

            person_month = PersonMonth.objects.get(
                person_year__person__cpr=self.person1.cpr,
                month=month,
                person_year__year__year=self.year.year,
            )
            person_month.benefit_paid = correct_benefit
            person_month.save()

    def test_isnan(self):
        self.assertTrue(isnan(np.float64(None)))
        self.assertFalse(isnan(np.float64(42)))


class QuarantineTest(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        person_month = PersonMonth.objects.get(
            person_year__year__year=cls.last_year.year,
            person_year__person__cpr=cls.person1.cpr,
            month=12,
        )

        # Simulate that person1 should only have gotten 2kr.
        # Thus the payout that he actually got is too high
        person_month.actual_year_benefit = 2
        person_month.save()

        # Person who is close to earning too little
        cls.person3 = Person.objects.create(
            name="Jens Gransen",
            cpr="3234567890",
        )

        # Person who is close to earning too much
        cls.person4 = Person.objects.create(
            name="Jens Fransen",
            cpr="2234567890",
        )

        for year in [cls.year, cls.last_year]:
            cls.person_year3 = PersonYear.objects.create(
                person=cls.person3,
                year=year,
                preferred_estimation_engine_a="InYearExtrapolationEngine",
                preferred_estimation_engine_b="InYearExtrapolationEngine",
            )

            cls.person_year4 = PersonYear.objects.create(
                person=cls.person4,
                year=year,
                preferred_estimation_engine_a="TwelveMonthsSummationEngine",
                preferred_estimation_engine_b="TwelveMonthsSummationEngine",
            )

        offset_gen = cycle([0.6, 1.4])
        salary = {cls.person3: 5_700, cls.person4: 41_000}
        for month_number in range(1, 13):
            offset = next(offset_gen)
            for person_year in [cls.person_year3, cls.person_year4]:
                month = PersonMonth.objects.create(
                    person_year=person_year,
                    month=month_number,
                    import_date=date.today(),
                    benefit_paid=1050,
                    prior_benefit_paid=1050 * (month_number - 1),
                    actual_year_benefit=1050 * 12,
                )

                MonthlyAIncomeReport.objects.create(
                    employer=cls.employer,
                    person_month=month,
                    salary_income=Decimal(salary[person_year.person] * offset),
                    month=month.month,
                    year=cls.last_year.year,
                    person=person_year.person,
                )

    def test_get_people_in_quarantine(self):
        df = get_people_in_quarantine(
            self.year.year, [self.person1.cpr, self.person2.cpr]
        )
        self.assertTrue(df.in_quarantine[self.person1.cpr])
        self.assertFalse(df.in_quarantine[self.person2.cpr])

    def test_in_quarantine_property(self):
        person_year_1 = PersonYear.objects.get(year=self.year, person=self.person1)
        person_year_2 = PersonYear.objects.get(year=self.year, person=self.person2)
        person_year_3 = PersonYear.objects.get(year=self.year, person=self.person3)
        person_year_4 = PersonYear.objects.get(year=self.year, person=self.person4)

        self.assertTrue(person_year_1.in_quarantine)
        self.assertFalse(person_year_2.in_quarantine)
        self.assertTrue(person_year_3.in_quarantine)
        self.assertTrue(person_year_4.in_quarantine)

        self.assertIn("Modtog for meget", person_year_1.quarantine_reason)
        self.assertEqual("-", person_year_2.quarantine_reason)
        self.assertIn("for tæt på bundgrænsen", person_year_3.quarantine_reason)
        self.assertIn("for tæt på øverste grænse", person_year_4.quarantine_reason)

    def test_get_people_who_might_earn_too_much_or_little(self):
        df = get_people_in_quarantine(
            self.year.year, [self.person3.cpr, self.person4.cpr]
        )
        self.assertTrue(df.loc[self.person3.cpr, "earns_too_little"])
        self.assertTrue(df.loc[self.person4.cpr, "earns_too_much"])
        self.assertFalse(df.loc[self.person3.cpr, "earns_too_much"])
        self.assertFalse(df.loc[self.person4.cpr, "earns_too_little"])

    def test_get_payout_date(self):
        payout_date = get_payout_date(2024, 11)

        self.assertEqual(payout_date.day, 19)
        self.assertEqual(payout_date.month, 11)
        self.assertEqual(payout_date.year, 2024)
