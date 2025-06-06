# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import copy
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from suila.management.commands.load_eskat import Command as LoadEskatCommand
from suila.models import ManagementCommands, PersonYear, Year


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


class TestLoadEskatTaxInformationCommand(TestCase):

    def setUp(self):
        super().setUp()

        self.json_data = [
            {
                "data": [
                    {
                        "cpr": "1111111111",
                        "year": 2025,
                        "taxScope": "FULL",
                        "startDate": "2025-01-01T00:00:00",
                        "endDate": "2025-12-31T00:00:00",
                        "catchSalePct": None,
                        "taxMunicipalityNumber": "32",
                        "cprMunicipalityCode": "956",
                        "regionNumber": None,
                        "regionName": "",
                        "districtName": "Nuuk",
                    }
                ],
                "message": (
                    "https://eskatdrift/eTaxCommonDataApi/api/"
                    "taxinformation/get/chunks/all/2025"
                ),
                "chunk": 1,
                "chunkSize": 1,
                "totalChunks": 2,
                "totalRecordsInChunks": 1,
            },
            {
                "data": [
                    {
                        "cpr": "2222222222",
                        "year": 2025,
                        "taxScope": "LIM",
                        "startDate": "2025-01-01T00:00:00",
                        "endDate": "2025-12-31T00:00:00",
                        "catchSalePct": None,
                        "taxMunicipalityNumber": "32",
                        "cprMunicipalityCode": "956",
                        "regionNumber": None,
                        "regionName": "",
                        "districtName": "Nuuk",
                    }
                ],
                "message": (
                    "https://eskatdrift/eTaxCommonDataApi/api/"
                    "taxinformation/get/chunks/all/2025"
                ),
                "chunk": 2,
                "chunkSize": 1,
                "totalChunks": 2,
                "totalRecordsInChunks": 1,
            },
        ]

    @patch("suila.integrations.eskat.client.EskatClient.get")
    def test_tax_scope(self, eskat_get: MagicMock):
        # Import two people (cpr="1111111111" and cpr="2222222222")
        eskat_get.side_effect = self.json_data
        call_command(ManagementCommands.LOAD_ESKAT, 2025, "taxinformation")

        # Assert that their tax-scopes were imported properly
        person_1 = PersonYear.objects.get(person__cpr="1111111111", year__year=2025)
        person_2 = PersonYear.objects.get(person__cpr="2222222222", year__year=2025)
        self.assertEqual(person_1.tax_scope, "FULD")
        self.assertEqual(person_2.tax_scope, "DELVIS")

        # Remove person2 from mandtal
        eskat_get.reset_mock()
        new_json_data = copy.deepcopy(self.json_data[0])
        new_json_data["totalChunks"] = 1
        eskat_get.side_effect = [new_json_data]

        # call the command again
        call_command(ManagementCommands.LOAD_ESKAT, 2025, "taxinformation")

        # Validate that the person is now missing from mandtal
        person_2.refresh_from_db()
        self.assertEqual(person_2.tax_scope, "INGEN_MANDTAL")

        # Add the person to mandtal again
        eskat_get.reset_mock()
        eskat_get.side_effect = self.json_data

        # call the command again
        call_command(ManagementCommands.LOAD_ESKAT, 2025, "taxinformation")

        # Validate that the tax scope of the person is back to normal
        person_2.refresh_from_db()
        self.assertEqual(person_2.tax_scope, "DELVIS")
