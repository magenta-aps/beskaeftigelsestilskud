# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils.translation import override

from suila.templatetags.date_tags import get_payment_date, month_name


class TestMonthName(SimpleTestCase):
    """Test the `suila.templatetags.date_tags.month_name` function."""

    def test_valid_input(self):
        with override("da"):
            self.assertEqual(month_name(5), "Maj")

    def test_invalid_input(self):
        # 1. Test that an invalid key does not raise an error
        self.assertIsNone(month_name(None))  # type: ignore
        # 2. Test that failing to capitalize the month name does not raise an error.
        # Replace `MONTHS` with a dictionary where the value cannot be capitalized.
        with patch("suila.templatetags.date_tags.dates.MONTHS", new=lambda: {0: None}):
            self.assertIsNone(month_name(0))


class TestGetPaymentDate(SimpleTestCase):
    """Test the `suila.templatetags.date_tags.get_payment_date` function."""

    def setUp(self):
        super().setUp()
        self.mock_person_month = MagicMock()
        self.mock_person_month.year = 2025
        self.mock_person_month.month = 1

    def test_valid_input(self):
        self.assertEqual(get_payment_date(self.mock_person_month), date(2025, 3, 18))
