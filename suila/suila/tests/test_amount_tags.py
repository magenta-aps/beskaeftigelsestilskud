# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils.translation import override

from suila.templatetags.amount_tags import format_amount


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
