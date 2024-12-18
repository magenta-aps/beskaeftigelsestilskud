# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from bf.akap import get_akap_u1a_entries, get_akap_u1a_items
from bf.management.commands.import_u1a_data import ImportResult


class AKAPTest(TestCase):
    @override_settings(AKAP_HOST="https://test.akap.sullissivik.gl")
    def test_get_akap_u1a_entries(self):
        u1a_entries = get_akap_u1a_entries(
            settings.AKAP_HOST, settings.AKAP_API_SECRET, limit=1  # type: ignore[misc]
        )

        for u1a in u1a_entries:
            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

        print(u1a_entries)


class ImportU1ADataTest(TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")

    @patch("bf.management.commands.import_u1a_data.Command._import_data")
    def test_handle(self, mock_import_data: MagicMock):

        # Mock the import result
        mock_import_data.return_value = ImportResult(
            new_entries=5, new_items=10, updated_entries=2, updated_items=3
        )

        # Call the command
        call_command("import_u1a_data", year=2023, cpr="123456", verbose=True)
        mock_import_data.assert_called_once_with(2023, "123456", True)
