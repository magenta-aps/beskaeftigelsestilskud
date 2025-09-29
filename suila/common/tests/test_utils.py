# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from itertools import cycle

from bs4 import BeautifulSoup
from common.models import User
from common.tests.test_mixins import TestViewMixin
from common.utils import (
    add_or_subtract_working_days,
    add_parameters_to_url,
    calculate_stability_score,
    calculate_stability_score_for_entire_year,
    camelcase_to_snakecase,
    get_income_as_dataframe,
    get_people_in_quarantine,
    get_user_who_pressed_pause,
    map_between_zero_and_one,
    to_dataframe,
)
from django.core.management import call_command as core_call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.timezone import get_current_timezone

from suila.integrations.prisme.b_tax import get_b_tax_file_timestamp
from suila.models import (
    Employer,
    IncomeEstimate,
    IncomeType,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    StandardWorkBenefitCalculationMethod,
    TaxInformationPeriod,
    Year,
)
from suila.tests.test_views import TimeContextMixin
from suila.views import PersonDetailView


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

    def test_get_user_who_pressed_pause(self):
        person = Person.objects.create(
            name="Jens Hansen", cpr="1234567890", paused=False
        )
        user = User.objects.create(username="test")
        person.paused = True
        person.save()
        history_item = person.history.order_by("-history_date").first()
        history_item.history_user = user
        history_item.save()
        self.assertEqual(get_user_who_pressed_pause(person), "skattestyrelsen")

    def test_get_user_who_pressed_pause_none(self):
        person = Person.objects.create(
            name="Jens Hansen", cpr="1234567890", paused=False
        )
        person.paused = True
        person.save()
        self.assertIsNone(get_user_who_pressed_pause(person))


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

        for counter in range(
            0, max(len(cls.unstable_income), len(cls.reasonably_stable_income))
        ):
            MonthlyIncomeReport.objects.create(
                salary_income=(
                    cls.reasonably_stable_income[counter]
                    if counter < len(cls.reasonably_stable_income)
                    else 0
                ),
                # TODO: Justér denne ift. hvilke felter der
                # indeholder medregnet B-indkomst
                capital_income=(
                    cls.unstable_income[counter]
                    if counter < len(cls.unstable_income)
                    else 0
                ),
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
        qs = MonthlyIncomeReport.objects.filter(a_income__gt=0).order_by("month")
        df = to_dataframe(
            qs, "person_month__person_year__person__cpr", {"a_income": float}
        )
        self.assertIn(self.person.cpr, df.index)
        self.assertEqual(list(df["a_income"].values), self.reasonably_stable_income)

    def test_get_income_as_dataframe(self):
        income_dict = get_income_as_dataframe(self.year.year)

        df_a = income_dict["A"]

        self.assertIn(self.person.cpr, df_a.index)

        for month_counter, amount in enumerate(self.reasonably_stable_income):
            month = month_counter + 1
            self.assertEqual(amount, df_a.loc[self.person.cpr, month])

    def test_calculate_stability_score_for_entire_year(self):
        df = calculate_stability_score_for_entire_year(self.year.year)

        # A income is reasonably stable
        self.assertLess(df.loc[self.person.cpr, "A"], 0.8)
        self.assertGreater(df.loc[self.person.cpr, "A"], 0.2)


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
            )

            person_year2 = PersonYear.objects.create(
                person=cls.person2,
                year=year,
                preferred_estimation_engine_a="TwelveMonthsSummationEngine",
            )
            person_years.append(person_year1)
            person_years.append(person_year2)

        cls.employer = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )

        for person_year in person_years:

            PersonYearAssessment.objects.create(
                person_year=person_year,
                valid_from=datetime(
                    person_year.year.year, 1, 1, 0, 0, 0, tzinfo=get_current_timezone()
                ),
                care_fee_income=Decimal(180000),
            )

            # Create periods covering the entire year under test, to verify the previous
            # behavior (reading `PersonYear.tax_scope`) is preserved.
            TaxInformationPeriod.objects.get_or_create(
                person_year=person_year,
                tax_scope="FULL",
                start_date=datetime(year.year, 1, 1),
                end_date=datetime(year.year, 12, 31),
            )

            for month_number in range(1, 13):
                month = PersonMonth.objects.create(
                    person_year=person_year,
                    month=month_number,
                    import_date=date.today(),
                    benefit_transferred=1050,
                    prior_benefit_transferred=1050 * (month_number - 1),
                    actual_year_benefit=1050 * 12,
                )
                income = MonthlyIncomeReport.objects.create(
                    person_month=month,
                    salary_income=Decimal(10000),
                    # disability_pension_income=Decimal(15000),
                    month=month.month,
                    year=cls.year.year,
                )

                # The InYearExtrapolationEngine estimates correctly
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * income.a_income,
                    actual_year_result=month_number * income.a_income,
                    engine="InYearExtrapolationEngine",
                    income_type=IncomeType.A,
                )

                # The TwelveMonthsSummationEngine does not estimate correctly
                # (At least in this dummy-data)
                IncomeEstimate.objects.create(
                    person_month=month,
                    estimated_year_result=12 * 9911,
                    actual_year_result=month_number * income.a_income,
                    engine="TwelveMonthsSummationEngine",
                    income_type=IncomeType.A,
                )

    def call_command(self, name, *args, **kwargs):
        stdout = StringIO()
        stderr = StringIO()
        core_call_command(
            name,
            *args,
            stdout=stdout,
            stderr=stderr,
            **kwargs,
        )
        return stdout, stderr


@override_settings(ENFORCE_QUARANTINE=True)
class QuarantineTest(TimeContextMixin, TestViewMixin, BaseTestCase):
    view_class = PersonDetailView

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
            )

            cls.person_year4 = PersonYear.objects.create(
                person=cls.person4,
                year=year,
                preferred_estimation_engine_a="TwelveMonthsSummationEngine",
            )

        offset_gen = cycle([0.6, 1.4])
        salary = {cls.person3: 5_700, cls.person4: 41_000}
        for month_number in range(1, 13):
            offset = next(offset_gen)
            for person in [cls.person3, cls.person4]:
                for year in [cls.year, cls.last_year]:
                    person_year = PersonYear.objects.get(person=person, year=year)
                    month = PersonMonth.objects.create(
                        person_year=person_year,
                        month=month_number,
                        import_date=date.today(),
                        benefit_transferred=1050,
                        prior_benefit_transferred=1050 * (month_number - 1),
                        actual_year_benefit=1050 * 12,
                    )

                    MonthlyIncomeReport.objects.create(
                        person_month=month,
                        salary_income=Decimal(salary[person_year.person] * offset),
                        month=month.month,
                        year=year,
                    )

    def test_get_people_in_quarantine(self):
        df = get_people_in_quarantine(
            self.year.year, [self.person1.cpr, self.person2.cpr]
        )
        self.assertTrue(df.in_quarantine[self.person1.cpr])
        self.assertFalse(df.in_quarantine[self.person2.cpr])

    @override_settings(QUARANTINE_IF_EARNS_TOO_LITTLE=True)
    @override_settings(QUARANTINE_IF_EARNS_TOO_MUCH=True)
    @override_settings(QUARANTINE_IF_WRONG_PAYOUT=True)
    def test_in_quarantine_property(self):
        person_year_1 = PersonYear.objects.get(year=self.year, person=self.person1)
        person_year_2 = PersonYear.objects.get(year=self.year, person=self.person2)
        person_year_3 = PersonYear.objects.get(year=self.year, person=self.person3)
        person_year_4 = PersonYear.objects.get(year=self.year, person=self.person4)

        self.assertTrue(person_year_1.in_quarantine)
        self.assertFalse(person_year_2.in_quarantine)
        self.assertTrue(person_year_3.in_quarantine)
        self.assertTrue(person_year_4.in_quarantine)

        self.assertIn("modtog for meget", person_year_1.quarantine_reason)
        self.assertEqual("-", person_year_2.quarantine_reason)
        self.assertIn("for tæt på bundgrænsen", person_year_3.quarantine_reason)
        self.assertIn("for tæt på øverste grænse", person_year_4.quarantine_reason)

    @override_settings(ENFORCE_QUARANTINE=False)
    def test_no_people_in_quarantine(self):
        df = get_people_in_quarantine(self.year.year, [])
        self.assertTrue(df.empty)

    @override_settings(QUARANTINE_IF_EARNS_TOO_LITTLE=False)
    @override_settings(QUARANTINE_IF_EARNS_TOO_MUCH=False)
    @override_settings(QUARANTINE_IF_WRONG_PAYOUT=False)
    def test_in_quarantine_property_turned_off(self):
        person_year_1 = PersonYear.objects.get(year=self.year, person=self.person1)
        person_year_2 = PersonYear.objects.get(year=self.year, person=self.person2)
        person_year_3 = PersonYear.objects.get(year=self.year, person=self.person3)
        person_year_4 = PersonYear.objects.get(year=self.year, person=self.person4)

        self.assertFalse(person_year_1.in_quarantine)
        self.assertFalse(person_year_2.in_quarantine)
        self.assertFalse(person_year_3.in_quarantine)
        self.assertFalse(person_year_4.in_quarantine)

    def test_get_people_who_might_earn_too_much_or_little(self):
        df = get_people_in_quarantine(
            self.year.year, [self.person3.cpr, self.person4.cpr]
        )
        self.assertTrue(df.loc[self.person3.cpr, "earns_too_little"])
        self.assertTrue(df.loc[self.person4.cpr, "earns_too_much"])
        self.assertFalse(df.loc[self.person3.cpr, "earns_too_much"])
        self.assertFalse(df.loc[self.person4.cpr, "earns_too_little"])

    @override_settings(QUARANTINE_IF_EARNS_TOO_LITTLE=True)
    @override_settings(QUARANTINE_IF_EARNS_TOO_MUCH=True)
    @override_settings(QUARANTINE_IF_WRONG_PAYOUT=True)
    @override_settings(QUARANTINE_WEIGHTS=[0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 1, 1])
    def test_quarantine_view(self):

        # Check that quarantine messages are displayed properly
        with self._time_context(year=2024, month=11):
            view, response = self.request_get(self.admin_user, pk=self.person1.pk)
            response.render()
            soup = str(BeautifulSoup(response.content, features="lxml"))
            self.assertIn("Du modtog for meget tilskud i 2023", soup)
            self.assertNotIn("Du tjente for tæt på bundgrænsen i 2023", soup)
            self.assertNotIn("Du tjente for tæt på øverste grænse i 2023", soup)

            view, response = self.request_get(self.admin_user, pk=self.person3.pk)
            response.render()
            soup = str(BeautifulSoup(response.content, features="lxml"))
            self.assertNotIn("Du modtog for meget tilskud i 2023", soup)
            self.assertIn("Du tjente for tæt på bundgrænsen i 2023", soup)
            self.assertNotIn("Du tjente for tæt på øverste grænse i 2023", soup)

            view, response = self.request_get(self.admin_user, pk=self.person4.pk)
            response.render()
            soup = str(BeautifulSoup(response.content, features="lxml"))
            self.assertNotIn("Du modtog for meget tilskud i 2023", soup)
            self.assertNotIn("Du tjente for tæt på bundgrænsen i 2023", soup)
            self.assertIn("Du tjente for tæt på øverste grænse i 2023", soup)

        # Check that payouts resume in december (because the weight = 10)
        with self._time_context(year=2024, month=12):
            view, response = self.request_get(self.admin_user, pk=self.person1.pk)
            response.render()
            soup = str(BeautifulSoup(response.content, features="lxml"))
            self.assertNotIn("Du modtog for meget tilskud i 2023", soup)
            self.assertNotIn("Du tjente for tæt på bundgrænsen i 2023", soup)
            self.assertNotIn("Du tjente for tæt på øverste grænse i 2023", soup)

        # It is not possible to be in quarantine in February (because the weight =1)
        with self._time_context(year=2024, month=2):
            view, response = self.request_get(self.admin_user, pk=self.person1.pk)
            response.render()
            soup = str(BeautifulSoup(response.content, features="lxml"))
            self.assertNotIn("Du modtog for meget tilskud i 2023", soup)
            self.assertNotIn("Du tjente for tæt på bundgrænsen i 2023", soup)
            self.assertNotIn("Du tjente for tæt på øverste grænse i 2023", soup)


class BTaxUtilsTest(TestCase):
    def test_get_b_tax_file_timestamp(self):
        timestamp = get_b_tax_file_timestamp("BSKAT_2025_207025_09-05-2025_093200.csv")
        self.assertEqual(timestamp.year, 2025)
        self.assertEqual(timestamp.month, 5)
        self.assertEqual(timestamp.day, 9)


class AddWorkingDaysTest(TestCase):
    def test_add_or_subtract_working_days(self):

        # 2025-10-3 is a friday.
        # So adding two working days gives Tuesday the 7th
        self.assertEqual(
            add_or_subtract_working_days(date(2025, 10, 3), 2),
            date(2025, 10, 7),
        )

        # 2025-12-24 is a christmas eve.
        # Second day of christmas is on a Friday.
        # So adding two working days gives Tuesday the 30th
        self.assertEqual(
            add_or_subtract_working_days(date(2025, 12, 24), 2),
            date(2025, 12, 30),
        )

        # 2026-05-01 is Great Prayer Day. Which Greenland still celebrates
        # Great prayer day is on a friday
        # So adding two working days to the thursday before gives Tuesday the 5th
        self.assertEqual(
            add_or_subtract_working_days(date(2026, 4, 30), 2),
            date(2026, 5, 5),
        )

        # The function can also be used to subtract working days
        # 2025-09-29 is a monday, so subtracting one day gives friday the 26th:
        self.assertEqual(
            add_or_subtract_working_days(date(2025, 9, 29), -1),
            date(2025, 9, 26),
        )
