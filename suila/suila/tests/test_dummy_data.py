# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.core.management import call_command
from django.test import TestCase

from suila.models import Person


class DummyDataTest(TestCase):
    def test_dummy_data_creation(self):
        call_command("load_dummy_calculation_method")
        call_command("create_dummy_data")

        persons = Person.objects.all()
        self.assertIn("Bruce Lee", [p.name for p in persons])
