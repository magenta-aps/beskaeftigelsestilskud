# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from django.template.defaultfilters import date as format_date
from django.test import SimpleTestCase
from django.utils import translation
from django.utils.formats import number_format as format_number
from django.utils.translation import get_language


class TestFormatDate(SimpleTestCase):
    value = date(2025, 1, 1)
    cases = [
        ("da", "1. januar 2025"),
        ("kl", "Januaarip 1, 2025"),
    ]

    def test_format_date(self):
        for locale, expected_value in self.cases:
            with self.subTest(locale=locale):
                translation.activate(locale)
                actual_value = format_date(self.value)
                self.assertEqual(expected_value, actual_value)


class TestFormatNumber(SimpleTestCase):
    value = 42_000_000.42
    cases = [
        ("da", "42.000.000,42"),
        ("kl", "42.000.000,42"),
    ]

    def test_format_number(self):
        for locale, expected_value in self.cases:
            with self.subTest(locale=locale):
                translation.activate(locale)
                self.assertEqual(get_language(), locale)
                actual_value = format_number(
                    self.value,
                    use_l10n=True,
                    force_grouping=True,
                )
                self.assertEqual(expected_value, actual_value)
