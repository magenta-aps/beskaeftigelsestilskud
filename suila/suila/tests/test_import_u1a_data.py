# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import StringIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from suila.management.commands.import_u1a_data import Command as ImportU1ADataCommand
from suila.models import Person, Year


class TestImportU1ADataCommand(TestCase):
    def setUp(self):
        super().setUp()
        self.command = ImportU1ADataCommand()
        self.command.stdout = StringIO()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year, _ = Year.objects.get_or_create(year=2025)
        cls.person1 = Person.objects.create(
            name="Jens Hansen",
            cpr="0101901177",
        )

    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items")
    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items_unique_cprs")
    def test_import_all(
        self,
        mock_get_akap_u1a_items_unique_cprs: MagicMock,
        mock_get_akap_u1a_items: MagicMock,
    ):
        mock_get_akap_u1a_items_unique_cprs.return_value = [self.person1.cpr]
        call_command(self.command)

        mock_get_akap_u1a_items_unique_cprs.assert_called_once_with(
            settings.AKAP_HOST, settings.AKAP_API_SECRET, self.year.year, fetch_all=True
        )
        mock_get_akap_u1a_items.assert_called_once_with(
            settings.AKAP_HOST,
            settings.AKAP_API_SECRET,
            year=self.year.year,
            cpr=self.person1.cpr,
            fetch_all=True,
        )

    # TODO: Make tests which verify the logic which handles the fetched U1A items
    # and creates MonthlyIncomeReports + updates PersonMonth sums
