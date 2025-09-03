# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date, datetime, timedelta
from decimal import Decimal
from operator import attrgetter
from unittest.mock import patch

import pytz
from common.tests.test_mixins import UserMixin
from django.test import TestCase
from django.utils import timezone

from suila.data import MonthlyIncomeData
from suila.models import (
    AnnualIncome,
    BTaxPayment,
    Employer,
    IncomeEstimate,
    IncomeType,
    JobLog,
    ManagementCommands,
    MonthlyIncomeReport,
    Note,
    PauseReasonChoices,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    PrismeAccountAlias,
    PrismeBatch,
    PrismeBatchItem,
    StandardWorkBenefitCalculationMethod,
    StatusChoices,
    TaxInformationPeriod,
    Year,
)


class ModelTest(TestCase):
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
        cls.year2 = Year.objects.create(year=2025)
        cls.person = Person.objects.create(
            name="Jens Hansen", cpr="1234567890", civil_state="G"
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        cls.person_year2 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year2,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        cls.month1 = PersonMonth.objects.create(
            person_year=cls.person_year, month=1, import_date=date.today()
        )
        cls.month2 = PersonMonth.objects.create(
            person_year=cls.person_year, month=2, import_date=date.today()
        )
        cls.month3 = PersonMonth.objects.create(
            person_year=cls.person_year, month=3, import_date=date.today()
        )
        cls.month4 = PersonMonth.objects.create(
            person_year=cls.person_year, month=4, import_date=date.today()
        )
        cls.month5 = PersonMonth.objects.create(
            person_year=cls.person_year, month=5, import_date=date.today()
        )
        cls.month6 = PersonMonth.objects.create(
            person_year=cls.person_year, month=6, import_date=date.today()
        )
        cls.month7 = PersonMonth.objects.create(
            person_year=cls.person_year, month=7, import_date=date.today()
        )
        cls.month8 = PersonMonth.objects.create(
            person_year=cls.person_year, month=8, import_date=date.today()
        )
        cls.month9 = PersonMonth.objects.create(
            person_year=cls.person_year, month=9, import_date=date.today()
        )
        cls.month10 = PersonMonth.objects.create(
            person_year=cls.person_year, month=10, import_date=date.today()
        )
        cls.month11 = PersonMonth.objects.create(
            person_year=cls.person_year, month=11, import_date=date.today()
        )
        cls.month12 = PersonMonth.objects.create(
            person_year=cls.person_year, month=12, import_date=date.today()
        )
        cls.year2month1 = PersonMonth.objects.create(
            person_year=cls.person_year2, month=1, import_date=date.today()
        )
        cls.year2month12 = PersonMonth.objects.create(
            person_year=cls.person_year2, month=12, import_date=date.today()
        )
        cls.employer1 = Employer.objects.create(
            name="Fredes Fisk",
            cvr=12345678,
        )
        cls.employer2 = Employer.objects.create(
            name="Ronnis Rejer",
            cvr=87654321,
        )
        cls.report1 = MonthlyIncomeReport.objects.create(
            person_month=cls.month1,
            salary_income=Decimal(10000),
            month=cls.month1.month,
            year=cls.year.year,
        )
        cls.report2 = MonthlyIncomeReport.objects.create(
            person_month=cls.month2,
            salary_income=Decimal(11000),
            month=cls.month2.month,
            year=cls.year.year,
        )
        cls.report3 = MonthlyIncomeReport.objects.create(
            person_month=cls.month3,
            salary_income=Decimal(12000),
            month=cls.month3.month,
            year=cls.year.year,
        )
        cls.report4 = MonthlyIncomeReport.objects.create(
            person_month=cls.month4,
            salary_income=Decimal(13000),
            month=cls.month4.month,
            year=cls.year.year,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month1,
            estimated_year_result=12 * 10000,
            actual_year_result=12 * 10000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report6 = MonthlyIncomeReport.objects.create(
            person_month=cls.month2,
            salary_income=Decimal(12000),
            month=cls.month2.month,
            year=cls.year.year,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month2,
            estimated_year_result=6 * (10000 + 11000) + 6 * (15000 + 12000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report7 = MonthlyIncomeReport.objects.create(
            person_month=cls.month3,
            salary_income=Decimal(10000),
            month=cls.month3.month,
            year=cls.year.year,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month3,
            estimated_year_result=4 * (10000 + 11000 + 12000)
            + 4 * (15000 + 12000 + 10000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report8 = MonthlyIncomeReport.objects.create(
            person_month=cls.month4,
            salary_income=Decimal(8000),
            month=cls.month4.month,
            year=cls.year.year,
        )
        IncomeEstimate.objects.create(
            person_month=cls.month4,
            estimated_year_result=3 * (10000 + 11000 + 12000 + 13000)
            + 3 * (15000 + 12000 + 10000 + 8000),
            actual_year_result=12 * 10000 + 12 * 15000,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        )
        cls.report9 = MonthlyIncomeReport.objects.create(
            person_month=cls.year2month1,
            salary_income=Decimal(8000),
            month=cls.year2month1.month,
            year=cls.year2.year,
        )
        cls.report10a = MonthlyIncomeReport.objects.create(
            person_month=cls.month10,
            salary_income=Decimal(-1000),
            month=cls.month10.month,
            year=cls.year.year,
        )
        cls.report10b = MonthlyIncomeReport.objects.create(
            person_month=cls.month10,
            salary_income=Decimal(1000),
            month=cls.month10.month,
            year=cls.year.year,
        )

        # No IncomeEstimate

        cls.final_settlement = AnnualIncome.objects.create(
            person_year=cls.person_year,
            account_tax_result=Decimal(13000),
        )
        cls.assessment1a = PersonYearAssessment.objects.create(
            person_year=cls.person_year,
            valid_from=datetime(
                year=cls.person_year.year_id,
                month=1,
                day=1,
                tzinfo=timezone.get_current_timezone(),
            ),
            goods_comsumption=Decimal(1000),
            operating_costs_catch_sale=Decimal(10000),
            catch_sale_market_income=Decimal(10000),
            catch_sale_factory_income=Decimal(10000),
        )
        cls.assessment1b = PersonYearAssessment.objects.create(
            person_year=cls.person_year,
            valid_from=datetime(
                year=cls.person_year.year_id,
                month=7,
                day=1,
                tzinfo=timezone.get_current_timezone(),
            ),
            goods_comsumption=Decimal(1200),
            operating_costs_catch_sale=Decimal(12000),
            catch_sale_market_income=Decimal(10000),
            catch_sale_factory_income=Decimal(10000),
        )
        cls.person_year.refresh_from_db()


class TestPrismeBatchItem(ModelTest):
    def test_amount_property(self):

        prisme_batch = PrismeBatch.objects.create(
            status="sent", export_date=date.today(), prefix=1
        )

        prisme_batch_item = PrismeBatchItem.objects.create(
            person_month=self.month1,
            prisme_batch=prisme_batch,
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800000031700&"
                "09+&1002&1100000101001111&1220250414&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )

        self.assertEqual(prisme_batch_item.amount, 317)

        with self.assertRaises(ValueError):
            prisme_batch_item.g68_content = "foo"
            prisme_batch_item.save()
            prisme_batch_item.amount


class TestStandardWorkBenefitCalculationMethod(ModelTest):

    def test_low(self):
        self.assertEqual(self.calc.calculate(Decimal("0")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("25000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("58000")), Decimal(0))

    def test_ramp_up(self):
        self.assertEqual(self.calc.calculate(Decimal("68000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("70000")), Decimal("350.00"))
        self.assertEqual(self.calc.calculate(Decimal("130000")), Decimal("10850.00"))
        self.assertEqual(self.calc.calculate(Decimal("158000")), Decimal("15750.00"))

    def test_plateau(self):
        self.assertEqual(self.calc.calculate(Decimal("158000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("200000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("250000")), Decimal("15750.00"))

    def test_ramp_down(self):
        self.assertEqual(self.calc.calculate(Decimal("250000")), Decimal("15750.00"))
        self.assertEqual(self.calc.calculate(Decimal("261000")), Decimal("15057.00"))
        self.assertEqual(self.calc.calculate(Decimal("340000")), Decimal("10080.00"))
        self.assertEqual(self.calc.calculate(Decimal("490000")), Decimal("630.00"))
        self.assertEqual(self.calc.calculate(Decimal("500000")), Decimal(0))

    def test_high(self):
        self.assertEqual(self.calc.calculate(Decimal("500000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("750000")), Decimal(0))
        self.assertEqual(self.calc.calculate(Decimal("1000000")), Decimal(0))

    def test_graph_points(self):
        self.assertEqual(
            self.calc.graph_points,
            [
                (Decimal("0"), Decimal("0")),
                (Decimal("68000.00"), Decimal("0")),
                (Decimal("158000.00"), Decimal("15750.00")),
                (Decimal("250000.00"), Decimal("15750.00")),
                (Decimal("500000.00"), Decimal("0")),
            ],
        )

        self.assertEqual(
            StandardWorkBenefitCalculationMethod(
                benefit_rate_percent=Decimal("17.50"),
                personal_allowance=Decimal("60000.00"),
                standard_allowance=Decimal("10000"),
                max_benefit=Decimal("100000.00"),  # much higher ceiling
                scaledown_rate_percent=Decimal("6.30"),
                scaledown_ceiling=Decimal("250000.00"),
            ).graph_points,
            [
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("70000.00"), Decimal("0.00")),
                (Decimal("250000.00"), Decimal("31500.00")),
                (Decimal("641428.57"), Decimal("75340.00")),
                (Decimal("1837301.59"), Decimal("0.00")),
            ],
        )

        self.assertEqual(
            StandardWorkBenefitCalculationMethod(
                benefit_rate_percent=Decimal("17.50"),
                personal_allowance=Decimal("60000.00"),
                standard_allowance=Decimal("10000.00"),
                max_benefit=Decimal("15750.00"),
                scaledown_rate_percent=Decimal("63.00"),  # Much higher scaledown
                scaledown_ceiling=Decimal("250000.00"),
            ).graph_points,
            [
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("70000.00"), Decimal("0.00")),
                (Decimal("160000.00"), Decimal("15750.00")),
                (Decimal("250000.00"), Decimal("15750.00")),
                (Decimal("275000.00"), Decimal("0.00")),
            ],
        )
        self.assertEqual(
            StandardWorkBenefitCalculationMethod(
                benefit_rate_percent=Decimal("10.00"),
                personal_allowance=Decimal("60000.00"),
                standard_allowance=Decimal("10000.00"),
                max_benefit=Decimal("15750.00"),
                scaledown_rate_percent=Decimal("10.00"),
                scaledown_ceiling=Decimal("250000.00"),
            ).graph_points,
            [
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("70000.00"), Decimal("0.00")),
                (Decimal("227500.00"), Decimal("15750.00")),
                (Decimal("250000.00"), Decimal("15750.00")),
                (Decimal("407500.00"), Decimal("0.00")),
            ],
        )

        self.assertEqual(
            StandardWorkBenefitCalculationMethod(
                benefit_rate_percent=Decimal("0.00"),
                personal_allowance=Decimal("60000.00"),
                standard_allowance=Decimal("10000"),
                max_benefit=Decimal("15750.00"),
                scaledown_rate_percent=Decimal("6.30"),
                scaledown_ceiling=Decimal("250000.00"),
            ).graph_points,
            [
                (Decimal("0.00"), Decimal("0.00")),
            ],
        )

        self.assertEqual(
            StandardWorkBenefitCalculationMethod(
                benefit_rate_percent=Decimal("17.50"),
                personal_allowance=Decimal("60000.00"),
                standard_allowance=Decimal("10000"),
                max_benefit=Decimal("15750.00"),
                scaledown_rate_percent=Decimal("0.00"),
                scaledown_ceiling=Decimal("250000.00"),
            ).graph_points,
            [
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("70000.00"), Decimal("0.00")),
                (Decimal("160000.00"), Decimal("15750.00")),
            ],
        )


class UserModelTest(UserMixin, ModelTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.normal_user.cpr = "1234567890"
        cls.normal_user.save()


class TestPerson(UserModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.person), "Jens Hansen / 1234567890")

    def test_borger_permissions(self):
        self.assertTrue(self.person.has_object_permissions(self.normal_user, ["view"]))
        self.assertFalse(
            self.person.has_object_permissions(self.normal_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.person.has_object_permissions(self.normal_user, []))
        qs = Person.filter_user_permissions(
            Person.objects.all(), self.normal_user, "view"
        )
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.person, qs)
        self.assertFalse(Person.has_model_permissions(self.normal_user, "view"))

    def test_staff_permissions(self):
        self.assertTrue(self.person.has_object_permissions(self.staff_user, ["view"]))
        self.assertFalse(
            self.person.has_object_permissions(self.staff_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.person.has_object_permissions(self.staff_user, []))
        qs = Person.filter_user_permissions(
            Person.objects.all(), self.staff_user, "view"
        )
        self.assertEqual(qs.count(), Person.objects.all().count())
        self.assertIn(self.person, qs)
        self.assertTrue(Person.has_model_permissions(self.staff_user, "view"))

    def test_other_permissions(self):
        self.assertFalse(self.person.has_object_permissions(self.other_user, ["view"]))
        self.assertFalse(
            self.person.has_object_permissions(self.other_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.person.has_object_permissions(self.other_user, []))
        qs = Person.filter_user_permissions(
            Person.objects.all(), self.other_user, "view"
        )
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.person, qs)
        self.assertFalse(Person.has_model_permissions(self.other_user, "view"))

    def test_anonymous_permissions(self):
        self.assertFalse(self.person.has_object_permissions(self.no_user, ["view"]))
        self.assertFalse(
            self.person.has_object_permissions(self.no_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.person.has_object_permissions(self.no_user, []))
        qs = Person.filter_user_permissions(Person.objects.all(), self.no_user, "view")
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.person, qs)
        self.assertFalse(Person.has_model_permissions(self.no_user, "view"))

    def test_full_address_splitted(self):
        self.assertEqual(self.person.full_address_splitted, [])
        self.person.full_address = "Imaneq 32, 3900 Nuuk"
        self.assertEqual(self.person.full_address_splitted, ["Imaneq 32", "3900 Nuuk"])

    def test_annual_income_estimate_last_change(self):
        # Step 1: Create a Person with an initial income estimate
        person = Person.objects.create(name="Test Person", annual_income_estimate=1000)

        # Step 2: Change an unrelated field (should not trigger detection)
        person.name = "Changed Name"
        person.save()

        # Step 3: Change the annual_income_estimate field
        person.annual_income_estimate = 120000
        person.save()
        expected_timestamp = (
            person.history.order_by("-history_date").first().history_date
        )

        # Step 4: Another unrelated change
        person.name = "Changed Again"
        person.save()

        # Step 5: Check that the property returns the timestamp from step 3
        self.assertEqual(
            person.last_change("annual_income_estimate"), expected_timestamp
        )

    def test_death(self):
        # Change state to F (fraskilt)
        self.person.civil_state = "F"
        self.person.save()
        # not paused
        self.assertFalse(self.person.paused)

        # Change state to D (død)
        self.person.civil_state = "D"
        self.person.save()
        # paused
        self.assertTrue(self.person.paused)
        self.assertEqual(self.person.pause_reason, PauseReasonChoices.DEATH)
        note = Note.objects.filter(
            personyear__person=self.person, author__isnull=True
        ).first()
        self.assertIsNotNone(note)
        self.assertEqual(
            note.text,
            f"Starter udbetalingspause\n"
            f"{PauseReasonChoices(PauseReasonChoices.DEATH).label}",
        )


class TestPersonYear(UserModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.person_year), "Jens Hansen / 1234567890 (2024)")

    def test_next(self):
        self.assertEqual(self.person_year.next, self.person_year2)
        self.assertIsNone(self.person_year2.next)

    def test_prev(self):
        self.assertEqual(self.person_year2.prev, self.person_year)
        self.assertIsNone(self.person_year.prev)

    def test_b_income(self):
        self.assertEqual(self.person_year.b_income, Decimal(10000))
        self.assertEqual(self.person_year2.b_income, Decimal(0))

    def test_borger_permissions(self):
        self.assertTrue(
            self.person_year.has_object_permissions(self.normal_user, ["view"])
        )
        self.assertFalse(
            self.person_year.has_object_permissions(self.normal_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(
                self.person_year.has_object_permissions(self.normal_user, [])
            )
        qs = PersonYear.filter_user_permissions(
            PersonYear.objects.all(), self.normal_user, "view"
        )
        self.assertEqual(
            qs.count(), PersonYear.objects.filter(person=self.person).count()
        )
        self.assertIn(self.person_year, qs)
        self.assertFalse(PersonYear.has_model_permissions(self.normal_user, "view"))

    def test_staff_permissions(self):
        self.assertTrue(
            self.person_year.has_object_permissions(self.staff_user, ["view"])
        )
        self.assertFalse(
            self.person_year.has_object_permissions(self.staff_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(
                self.person_year.has_object_permissions(self.staff_user, [])
            )
        qs = PersonYear.filter_user_permissions(
            PersonYear.objects.all(), self.staff_user, "view"
        )
        self.assertEqual(qs.count(), PersonYear.objects.all().count())
        self.assertIn(self.person_year, qs)
        self.assertTrue(PersonYear.has_model_permissions(self.staff_user, "view"))

    def test_other_permissions(self):
        self.assertFalse(
            self.person_year.has_object_permissions(self.other_user, ["view"])
        )
        self.assertFalse(
            self.person_year.has_object_permissions(self.other_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(
                self.person_year.has_object_permissions(self.other_user, [])
            )
        qs = PersonYear.filter_user_permissions(
            PersonYear.objects.all(), self.other_user, "view"
        )
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.person_year, qs)
        self.assertFalse(PersonYear.has_model_permissions(self.other_user, "view"))

    def test_anonymous_permissions(self):
        self.assertFalse(
            self.person_year.has_object_permissions(self.no_user, ["view"])
        )
        self.assertFalse(
            self.person_year.has_object_permissions(self.no_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.person_year.has_object_permissions(self.no_user, []))
        qs = PersonYear.filter_user_permissions(
            PersonYear.objects.all(), self.no_user, "view"
        )
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.person_year, qs)
        self.assertFalse(PersonYear.has_model_permissions(self.no_user, "view"))

    def test_expenses_sum(self):
        self.assertEqual(
            self.person_year.catchsale_expenses,
            Decimal(12000),
        )
        self.assertEqual(
            self.person_year.b_expenses,
            Decimal(1200),
        )


class TestPersonMonth(UserModelTest):

    def test_shortcuts(self):
        self.assertEqual(self.month1.year, 2024)

    def test_string_methods(self):
        self.assertEqual(str(self.month1), "2024/1 (Jens Hansen / 1234567890)")

    def test_amount_sum(self):
        self.assertEqual(self.month1.amount_sum, Decimal(10000))
        self.assertEqual(self.month2.amount_sum, Decimal(11000 + 12000))
        self.assertEqual(self.month3.amount_sum, Decimal(12000 + 10000))
        self.assertEqual(self.month4.amount_sum, Decimal(13000 + 8000))

    def test_next(self):
        self.assertEqual(self.month1.next, self.month2)
        self.assertEqual(self.month12.next, self.year2month1)
        self.assertIsNone(self.year2month1.next)
        self.assertIsNone(self.year2month12.next)

    def test_prev(self):
        self.assertEqual(self.month2.prev, self.month1)
        self.assertEqual(self.year2month1.prev, self.month12)
        self.assertIsNone(self.month1.prev)
        self.month11.delete()
        self.assertIsNone(self.month12.prev)

    def test_borger_permissions(self):
        self.assertTrue(self.month1.has_object_permissions(self.normal_user, ["view"]))
        self.assertFalse(
            self.month1.has_object_permissions(self.normal_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.month1.has_object_permissions(self.normal_user, []))
        qs = PersonMonth.filter_user_permissions(
            PersonMonth.objects.all(), self.normal_user, "view"
        )
        self.assertEqual(
            qs.count(),
            PersonMonth.objects.filter(person_year__person=self.person).count(),
        )
        self.assertIn(self.month1, qs)
        self.assertFalse(PersonMonth.has_model_permissions(self.normal_user, "view"))

    def test_staff_permissions(self):
        self.assertTrue(self.month1.has_object_permissions(self.staff_user, ["view"]))
        self.assertFalse(
            self.month1.has_object_permissions(self.staff_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.month1.has_object_permissions(self.staff_user, []))
        qs = PersonMonth.filter_user_permissions(
            PersonMonth.objects.all(), self.staff_user, "view"
        )
        self.assertEqual(qs.count(), PersonMonth.objects.all().count())
        self.assertIn(self.month1, qs)
        self.assertTrue(PersonMonth.has_model_permissions(self.staff_user, "view"))

    def test_other_permissions(self):
        self.assertFalse(self.month1.has_object_permissions(self.other_user, ["view"]))
        self.assertFalse(
            self.month1.has_object_permissions(self.other_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.month1.has_object_permissions(self.other_user, []))
        qs = PersonMonth.filter_user_permissions(
            PersonMonth.objects.all(), self.other_user, "view"
        )
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.month1, qs)
        self.assertFalse(PersonMonth.has_model_permissions(self.other_user, "view"))

    def test_anonymous_permissions(self):
        self.assertFalse(self.month1.has_object_permissions(self.no_user, ["view"]))
        self.assertFalse(
            self.month1.has_object_permissions(self.no_user, ["view", "add"])
        )
        with self.assertRaises(ValueError):
            self.assertFalse(self.month1.has_object_permissions(self.no_user, []))
        qs = PersonMonth.filter_user_permissions(
            PersonMonth.objects.all(), self.no_user, "view"
        )
        self.assertEqual(qs.count(), 0)
        self.assertNotIn(self.month1, qs)
        self.assertFalse(PersonMonth.has_model_permissions(self.no_user, "view"))

    def test_signal(self):
        self.assertTrue(self.month1.signal)
        self.assertTrue(self.month2.signal)
        self.assertTrue(self.month3.signal)
        self.assertTrue(self.month4.signal)
        self.assertFalse(self.month12.signal)
        self.assertTrue(self.month10.signal)
        income_qs = PersonMonth.signal_qs(
            self.person_year.personmonth_set.all()
        ).filter(has_signal=True)
        self.assertIn(self.month1, income_qs)
        self.assertIn(self.month2, income_qs)
        self.assertIn(self.month3, income_qs)
        self.assertIn(self.month4, income_qs)
        self.assertNotIn(self.month12, income_qs)
        self.assertIn(self.month10, income_qs)

    @patch("suila.models.datetime")
    def test_paused_property(self, datetime_mock):
        datetime_mock.side_effect = datetime
        datetime_mock.now.return_value = pytz.utc.localize(datetime(2024, 5, 1))

        self.person.paused = True
        self.person.save()
        self.person.refresh_from_db()
        history_entries = self.person.history.all().order_by("-history_date")

        for index, h in enumerate(history_entries):
            if index == 0:
                h.history_date = datetime(2024, 4, 15, 0, 0, 0)
            else:
                h.history_date = datetime(2024, 3, 10, 0, 0, 0)
            h.save()

        # The person did not exist yet on the 1st of March.
        # We therefore assume that he was not paused.
        self.assertFalse(self.month1.paused)

        # On the 1st of April he exists, but was not paused
        self.assertFalse(self.month2.paused)

        # On the 1st of May he is paused
        self.assertTrue(self.month3.paused)

        # December is a future month. We assume that he is still paused by then.
        self.assertTrue(self.month12.paused)

        # Simulate that we calculated benefit on the 16th of April for someone else
        job_log = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_BENEFIT,
            runtime_end=datetime(2024, 4, 16, 12, 30, 0),
            status=StatusChoices.SUCCEEDED,
            cpr_param="35435252",
        )

        job_log.runtime = datetime(2024, 4, 16, 12, 0, 0)
        job_log.save()

        # The function still checks for the first of april
        self.assertFalse(self.month2.paused)

        # Simulate that we calculated benefit for this person on the 16th of April
        job_log = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_BENEFIT,
            runtime_end=datetime(2024, 4, 16, 12, 30, 0),
            status=StatusChoices.SUCCEEDED,
            cpr_param=self.person.cpr,
        )

        job_log.runtime = datetime(2024, 4, 16, 12, 0, 0)
        job_log.save()

        # Now the function checks if the person was paused on the 16th of April instead.
        self.assertTrue(self.month2.paused)

        # If the user changes cpr (for some reason):
        # We can no longer find the calculation job for him and return False again
        # Because he was not paused on the first of April
        self.person.cpr = "qqqww"
        self.person.save()
        self.month2.refresh_from_db()
        self.assertFalse(self.month2.paused)

        # Simulate that we calculated benefit for everyone on the 16th of April
        job_log = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_BENEFIT,
            runtime_end=datetime(2024, 4, 16, 12, 30, 0),
            status=StatusChoices.SUCCEEDED,
        )

        job_log.runtime = datetime(2024, 4, 16, 12, 0, 0)
        job_log.save()

        # Now the function again checks if the person was paused on the 16th of April.
        self.assertTrue(self.month2.paused)


class TestEmployer(ModelTest):

    def test_string_methods(self):
        self.assertEqual(str(self.employer1), "Fredes Fisk (12345678)")


class TestIncomeReport(ModelTest):

    def test_constructor(self):
        try:
            m = MonthlyIncomeReport()
        except Exception:
            self.fail("Raised exception on constructor with no input")
        try:
            m.person_month = self.month1
            m.save()
        except Exception:
            self.fail("Raised exception on constructor with no input")

    def test_shortcuts(self):
        self.assertEqual(self.report1.person_year, self.person_year)
        self.assertEqual(self.report1.person, self.person)
        self.assertEqual(self.report1.year, 2024)
        self.assertEqual(self.report1.month, 1)

    def test_string_methods(self):
        self.assertEqual(
            str(self.report1),
            "MonthlyIncomeReport for 2024/1 (Jens Hansen / 1234567890) (None)",
        )

    def test_annotate_month(self):
        qs = MonthlyIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(MonthlyIncomeReport.annotate_month(qs).first().f_month, 1)

    def test_annotate_year(self):
        qs = MonthlyIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(MonthlyIncomeReport.annotate_year(qs).first().f_year, 2024)

    def test_annotate_person_year(self):
        qs = MonthlyIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(
            MonthlyIncomeReport.annotate_person_year(qs).first().f_person_year,
            self.person_year.pk,
        )

    def test_annotate_person(self):
        qs = MonthlyIncomeReport.objects.filter(pk=self.report1.pk)
        self.assertEqual(
            MonthlyIncomeReport.annotate_person(qs).first().f_person,
            self.person.pk,
        )

    def test_data_income(self):
        data = MonthlyIncomeData(
            month=6,
            year=2024,
            a_income=Decimal(15000),
            u_income=Decimal(5000),
            person_pk=1,
            person_month_pk=1,
            person_year_pk=1,
            signal=True,
        )
        self.assertEqual(data.amount, Decimal(20000))

    def test_post_save(self):
        report = self.report1
        old_amount = report.a_income
        new_amount = 200
        old_amount_sum = report.person_month.amount_sum
        report.salary_income = new_amount
        report.save(update_fields=("a_income",))
        self.assertEqual(
            report.person_month.amount_sum, old_amount_sum - old_amount + new_amount
        )

        # post_save is not triggered when the amount is not updated
        report.a_income = 1122
        report.save(update_fields=("catchsale_income",))
        self.assertEqual(
            report.person_month.amount_sum, old_amount_sum - old_amount + new_amount
        )


class EstimationTest(ModelTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.result1, _ = IncomeEstimate.objects.update_or_create(
            engine="InYearExtrapolationEngine",
            person_month=cls.month1,
            income_type=IncomeType.A,
            defaults={
                "estimated_year_result": 1200,
                "actual_year_result": 1400,
            },
        )
        cls.result2, _ = IncomeEstimate.objects.update_or_create(
            engine="InYearExtrapolationEngine",
            person_month=cls.month1,
            income_type=IncomeType.U,
            defaults={
                "estimated_year_result": 150,
                "actual_year_result": 200,
            },
        )

    def test_str(self):
        self.assertEqual(
            str(self.result1),
            "InYearExtrapolationEngine (2024/1 (Jens Hansen / 1234567890)) (A)",
        )

    def test_annotate_month(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(IncomeEstimate.annotate_month(qs).first().f_month, 1)

    def test_annotate_year(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(IncomeEstimate.annotate_year(qs).first().f_year, 2024)

    def test_annotate_person_year(self):
        qs = IncomeEstimate.objects.filter(pk=self.result1.pk)
        self.assertEqual(
            IncomeEstimate.annotate_person_year(qs).first().f_person_year,
            self.person_year.pk,
        )

    def test_qs_offset(self):
        qs = IncomeEstimate.objects.filter(pk__in=[self.result1.pk, self.result2.pk])
        self.assertEqual(IncomeEstimate.qs_offset(qs), Decimal(250 / 1600))

    def test_qs_offset_actual_year_result_is_zero(self):
        self.result1.actual_year_result = None
        self.result1.save()
        self.result1.refresh_from_db()

        qs = IncomeEstimate.objects.filter(pk__in=[self.result1.pk, self.result2.pk])
        self.assertEqual(IncomeEstimate.qs_offset(qs), Decimal(1150 / 200))


class TestPrismeAccountAlias(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.instance = PrismeAccountAlias.objects.create(
            alias="1000452406141010100002420401951900025",
            tax_municipality_location_code="961",
            tax_year=2020,
        )

    def test_str(self):
        self.assertEqual(str(self.instance), self.instance.alias)

    def test_tax_municipality_five_digit_code_property(self):
        self.assertEqual(self.instance.tax_municipality_five_digit_code, "19000")


class TestBTaxPayment(ModelTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.instance = BTaxPayment.objects.create(
            person_month=cls.month1,
            amount_paid=Decimal("900"),
            amount_charged=Decimal("1000"),
            date_charged=date(2020, 1, 1),
            rate_number=1,
            filename="",
            serial_number=1,
        )

    def test_str(self):
        self.assertEqual(str(self.instance), f"{self.month1}: 900")


class TestPersonYearAssessment(ModelTest):
    def test_update_latest(self):
        assessment1 = PersonYearAssessment.objects.create(
            person_year=self.person_year, valid_from=timezone.now() - timedelta(days=30)
        )
        self.assertTrue(assessment1.latest)
        assessment2 = PersonYearAssessment.objects.create(
            person_year=self.person_year, valid_from=timezone.now() - timedelta(days=20)
        )
        self.assertTrue(assessment1.latest)
        assessment1.refresh_from_db()
        self.assertFalse(assessment1.latest)
        assessment2.refresh_from_db()
        self.assertTrue(assessment2.latest)


class TestTaxInformationPeriod(ModelTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person2 = Person.objects.create(name="Hans Jensen", cpr="0987654321")
        cls.person2_person_year = PersonYear.objects.create(
            person=cls.person2,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        PersonMonth.objects.bulk_create(
            [
                PersonMonth(
                    person_year=cls.person2_person_year,
                    month=month,
                    import_date=date.today(),
                )
                for month in range(1, 13)
            ]
        )
        cls.period1 = TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls._get_datetime(2, 15),  # Feb 15
            end_date=cls._get_datetime(4, 15),  # Apr 15
        )

    @classmethod
    def _get_datetime(cls, month: int, day: int):
        return datetime(
            cls.year.year, month, day, tzinfo=timezone.get_current_timezone()
        )

    def test_get_person_month_filter_annotation(self):
        # Arrange: for each month under test, describe the expected result of the
        # annotation.
        test_cases = [
            # The test cases consist of month numbers along with the expected values of
            # the annotation for `self.person_year` and `self.person2_person_year`.
            # (`self.person2_person_year` have no `TaxInformationPeriod` objects, so the
            # annotation is always expected to be False, regardless of the month.)
            (1, [False, False]),  # no overlapping period
            (2, [False, False]),  # periodestart >= d 15
            (3, [True, False]),  # completely overlapping period
            (4, [False, False]),  # borgeren er der ikke den sidste dag i måneden
        ]
        for month, expected_result in test_cases:
            with self.subTest(month=month, expected_result=expected_result):
                # Act
                annotated_queryset = (
                    PersonMonth.objects.filter(
                        person_year__in=(self.person_year, self.person2_person_year),
                        month=month,
                    )
                    .annotate(
                        result=TaxInformationPeriod.get_person_month_filter_annotation(
                            self.year.year, month
                        )
                    )
                    .order_by("person_year")
                )
                # Assert
                self.assertQuerySetEqual(
                    annotated_queryset,
                    expected_result,
                    transform=attrgetter("result"),
                )

    def get_person_month(self, month):
        return PersonMonth.objects.annotate(
            taxable=TaxInformationPeriod.get_person_month_filter_annotation(
                self.year.year, month
            )
        ).get(
            person_year=self.person_year,
            month=month,
        )

    def test_get_person_month_filter_annotation_arrival(self):
        # I en måned, hvor en ny skatteborger ankommer til Grønland,
        # skal vedkommende anses for fuldt skattepligtig, hvis perioden starter
        # senest den 15. Hvis periodestart >= d 15., skal vedkommende ikke have noget.
        # https://redmine.magenta.dk/issues/65645#note-48
        month = 2
        person_month = self.get_person_month(month)
        self.assertEqual(self.period1.start_date.day, 15)
        self.assertFalse(person_month.taxable)

        self.period1.start_date = self._get_datetime(2, 14)
        self.period1.save()

        person_month = self.get_person_month(month)
        self.assertEqual(self.period1.start_date.day, 14)
        self.assertTrue(person_month.taxable)

    def test_get_person_month_filter_annotation_exit(self):
        # Ved periodens slutning er afskæringsdatoen den sidste dag i måneden.
        # Er skatteborgeren der ikke den sidste dag i måneden, skal der ikke udbetales
        # noget for den måned.
        # https://redmine.magenta.dk/issues/65645#note-48
        month = 4
        person_month = self.get_person_month(month)
        self.assertEqual(self.period1.end_date.day, 15)
        self.assertFalse(person_month.taxable)

        self.period1.end_date = self._get_datetime(4, 30)
        self.period1.save()

        person_month = self.get_person_month(month)
        self.assertEqual(self.period1.end_date.day, 30)
        self.assertTrue(person_month.taxable)

        self.period1.end_date = self._get_datetime(4, 29)
        self.period1.save()

        person_month = self.get_person_month(month)
        self.assertEqual(self.period1.end_date.day, 29)
        self.assertFalse(person_month.taxable)

    def test_get_person_month_filter_annotation_other_required_tax_scope(self):
        # Act
        month = 2
        annotated_queryset = (
            PersonMonth.objects.filter(
                person_year__in=(self.person_year, self.person2_person_year),
                month=month,
            )
            .annotate(
                result=TaxInformationPeriod.get_person_month_filter_annotation(
                    self.year.year, month, required_tax_scope="LIM"
                )
            )
            .order_by("person_year")
        )
        # Assert: the annotation is always False, as no `TaxInformationPeriod` objects
        # match the specified `required_tax_scope`.
        self.assertQuerySetEqual(
            annotated_queryset,
            [False, False],
            transform=attrgetter("result"),
        )

    def test_get_person_month_filter_annotation_for_entire_year(self):

        # self.period1 runs from feb to April
        self.period1.start_date = self._get_datetime(2, 10)
        self.period1.end_date = self._get_datetime(4, 30)
        self.period1.save()

        # Meaning the person is fully-taxable for three months.
        #
        # January:
        #    - The person is not fully-taxable in jan. but we assume that he is for the
        #      remainder of the year. Therefore months_with_full_tax_scope = 11
        # February:
        #    - The person is fully-taxable in feb. and we assume that he is for the
        #      remainder of the year. Therefore months_with_full_tax_scope = 11
        # May:
        #    - The person is not fully-taxable in may but we assume that he is for the
        #      remainder of the year. He was also not fully taxable in january.
        #      but he was fully taxable from feb. to april.
        #      Therefore months_with_full_tax_scope = 10
        expected_results = [
            {"month": 1, "months_with_full_tax_scope": 11},
            {"month": 2, "months_with_full_tax_scope": 11},
            {"month": 3, "months_with_full_tax_scope": 11},
            {"month": 4, "months_with_full_tax_scope": 11},
            {"month": 5, "months_with_full_tax_scope": 10},
            {"month": 6, "months_with_full_tax_scope": 9},
            {"month": 7, "months_with_full_tax_scope": 8},
            {"month": 8, "months_with_full_tax_scope": 7},
            {"month": 9, "months_with_full_tax_scope": 6},
            {"month": 10, "months_with_full_tax_scope": 5},
            {"month": 11, "months_with_full_tax_scope": 4},
            {"month": 12, "months_with_full_tax_scope": 3},
        ]

        for expected_result in expected_results:

            # Act
            month = expected_result["month"]

            # self.person2_person_year always has zero months with full-tax scope
            # because he does not have any taxinformation periods
            # But we assume all future months to have full tax-scope
            # So in january we assume he has 11 full-tax-scope-months. And so on.
            months_with_full_tax_scope_person_2 = 12 - month

            months_with_full_tax_scope = (
                TaxInformationPeriod.get_person_month_filter_annotation_for_entire_year(
                    self.year.year, month
                )
            )

            annotated_queryset = (
                PersonMonth.objects.filter(
                    person_year__in=(self.person_year, self.person2_person_year),
                    month=month,
                )
                .annotate(months_with_full_tax_scope=months_with_full_tax_scope)
                .order_by("person_year")
            )

            self.assertQuerySetEqual(
                annotated_queryset,
                [
                    expected_result["months_with_full_tax_scope"],
                    months_with_full_tax_scope_person_2,
                ],
                transform=attrgetter("months_with_full_tax_scope"),
            )
