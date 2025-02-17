# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.test import SimpleTestCase

from suila.templatetags.cpr_tags import format_cpr


class TestFormatCpr(SimpleTestCase):
    """Test the `suila.templatetags.cpr_tags.format_cpr` function."""

    def test_valid_input(self):
        self.assertEqual(format_cpr("0101012222"), "010101-2222")

    def test_valid_input_int(self):
        self.assertEqual(format_cpr(311270_0000), "311270-0000")
