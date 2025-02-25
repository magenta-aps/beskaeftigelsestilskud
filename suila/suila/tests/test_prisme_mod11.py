# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.test import SimpleTestCase

from suila.integrations.prisme.mod11 import validate_mod11


class TestValidateMod11(SimpleTestCase):
    def test_valid_cpr_returns_true(self):
        # Valid CPR generated using:
        # https://janosh.neocities.org/javascript-personal-id-check-and-generator/
        self.assertTrue(validate_mod11("0101000028"))

    def test_invalid_cpr_returns_false(self):
        # Test against "valid CPR minus 1"
        self.assertFalse(validate_mod11("0101000027"))
