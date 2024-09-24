# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from common.utils import (
    add_parameters_to_url,
    calculate_stability_score,
    calculate_stability_score_for_entire_year,
    get_income_as_dataframe,
    map_between_zero_and_one,
    to_dataframe,
)
from django.test import TestCase

from bf.models import (
    Employer,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)


class TestUtils(TestCase):
    def test_add_parameters_to_url(self):
        url = "http://foo.com"
        parameters_to_add = {"mucki": 1, "bar": "test"}

        url_with_parameters = add_parameters_to_url(url, parameters_to_add)
        self.assertEqual(url_with_parameters, "http://foo.com?mucki=1&bar=test")


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
                amount=amount,
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

    def test_to_dataframe(self):
        qs = MonthlyAIncomeReport.objects.all()
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
