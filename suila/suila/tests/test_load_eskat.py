# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import StringIO
from unittest.mock import patch

from django.test import TestCase

from suila.management.commands.load_eskat import Command as LoadEskatCommand
from suila.models import Year


class TestLoadEskatCommand(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year, _ = Year.objects.get_or_create(year=2024)

    def setUp(self):
        super().setUp()
        self.command = LoadEskatCommand()
        self.command.stdout = StringIO()

    @patch("suila.management.commands.load_eskat.EskatClient")
    def test_type_option(self, mock_eskat_client):
        """Verify that all valid values for `type` run without errors"""

        # Arrange
        for type in (
            "annualincome",
            "expectedincome",
            "monthlyincome",
            "taxinformation",
        ):
            with self.subTest(type=type):
                # Act
                self.command._handle(
                    year=self.year.year,
                    month=1,
                    type=type,
                    cpr=None,
                    verbosity=2,
                    fetch_chunk_size=20,
                    insert_chunk_size=20,
                )
