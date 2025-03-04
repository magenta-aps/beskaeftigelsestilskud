# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from common.fields import CPRField
from django.test import TestCase


class TestCPRField(TestCase):
    def test_to_python(self):
        field = CPRField()
        self.assertEqual(field.to_python("1234567890"), "1234567890")
        self.assertEqual(field.to_python("123456-7890"), "1234567890")
        self.assertEqual(field.to_python(" 123456-7890 "), "1234567890")
        self.assertEqual(field.to_python(None), "")
