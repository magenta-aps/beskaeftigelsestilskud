# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils.translation import override

from suila.models import Person, PersonMonth, PersonYear, PrismeBatchItem, Year
from suila.templatetags.amount_tags import display_amount, format_amount


class TestFormatAmount(SimpleTestCase):
    """Test the `suila.templatetags.amount_tags.format_amount` function."""

    def test_valid_input(self):
        with override("da"):
            self.assertEqual(
                format_amount(Decimal("123456789.876"), 4), "123.456.789,8760 kr."
            )

    def test_valid_input_none(self):
        with override("da"):
            self.assertEqual(format_amount(None, 4), "-")


class TestDisplayAmount(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year = Year.objects.create(year=2025)
        cls.person = Person.objects.create(cpr="0101011234")
        cls.person_year = PersonYear.objects.create(year=cls.year, person=cls.person)

        cls.person_month = PersonMonth.objects.create(
            person_year=cls.person_year,
            month=1,
            import_date="2022-01-01",
            benefit_calculated=123,
            benefit_transferred=456,
        )

    @patch("suila.templatetags.amount_tags.datetime")
    def test_past_months_zero(self, datetime_mock):

        datetime_mock.date.today.return_value = datetime.date(2025, 5, 2)
        datetime_mock.date.side_effect = datetime.date

        # If a person-month is in the past do not show an amount in the table
        # (If it has no prisme-batch-item)
        amount = display_amount(self.person_month)["value"]
        self.assertEqual(amount, None)

        # Otherwise, we can show the amount
        self.person_month.month = 3
        amount = display_amount(self.person_month)["value"]
        self.assertEqual(amount, 123)

    @patch("suila.templatetags.amount_tags.datetime")
    def test_amount_with_prisme_item(self, datetime_mock):

        datetime_mock.date.today.return_value = datetime.date(2025, 2, 2)
        datetime_mock.date.side_effect = datetime.date

        self.assertEqual(display_amount(self.person_month)["value"], 123)
        self.person_month.prismebatchitem = PrismeBatchItem(
            status=PrismeBatchItem.PostingStatus.Posted
        )
        self.assertEqual(display_amount(self.person_month)["value"], 456)
