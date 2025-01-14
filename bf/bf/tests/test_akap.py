# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from bf.akap import (
    AKAPU1A,
    URL_U1A_ITEMS,
    URL_U1A_LIST,
    AKAPU1AItem,
    get_akap_u1a_entries,
    get_akap_u1a_items,
    get_akap_u1a_items_unique_cprs,
)


class TestAKAPAPI(unittest.TestCase):
    def setUp(self):
        self.host = "https://test.api"
        self.auth_token = "test-token"

    @patch("bf.akap.requests.get")
    def test_get_akap_u1a_entries(self, mock_get: MagicMock):
        # Mock response data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 1,
            "items": [
                {
                    "id": 1,
                    "navn": "Test Company",
                    "revisionsfirma": "Test Audit",
                    "virksomhedsnavn": "Test Business",
                    "cvr": "12345678",
                    "email": "test@example.com",
                    "regnskabsår": 2023,
                    "u1_udfyldt": True,
                    "udbytte": "100000.00",
                    "noter": "Test notes",
                    "by": "Copenhagen",
                    "dato": "2023-01-01",
                    "underskriftsberettiget": "Test Person",
                    "oprettet": "2023-01-01T12:00:00",
                    "oprettet_af_cpr": "1234567890",
                    "oprettet_af_cvr": "12345678",
                }
            ],
        }
        mock_get.return_value = mock_response

        year = 2023
        cpr = "1234567890"
        entries = get_akap_u1a_entries(self.host, self.auth_token, year=year, cpr=cpr)

        mock_get.assert_called_once_with(
            self.host + URL_U1A_LIST,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 50, "offset": 0, "regnskabsår": year, "cpr": cpr},
        )
        self.assertEqual(len(entries), 1)
        self.assertIsInstance(entries[0], AKAPU1A)
        self.assertEqual(entries[0].navn, "Test Company")

    @patch("bf.akap.requests.get")
    def test_get_akap_u1a_entries_with_pagination(self, mock_get):
        # Mock responses for pagination
        first_response = MagicMock()
        first_response.status_code = 200
        first_response.json.return_value = {
            "count": 3,
            "items": [
                {
                    "id": 1,
                    "navn": "Test Company 1",
                    "revisionsfirma": "Test Audit",
                    "virksomhedsnavn": "Test Business",
                    "cvr": "12345678",
                    "email": "test1@example.com",
                    "regnskabsår": 2023,
                    "u1_udfyldt": True,
                    "udbytte": "100000.00",
                    "noter": "Test notes",
                    "by": "Copenhagen",
                    "dato": "2023-01-01",
                    "underskriftsberettiget": "Test Person",
                    "oprettet": "2023-01-01T12:00:00",
                    "oprettet_af_cpr": "1234567890",
                    "oprettet_af_cvr": "12345678",
                },
            ],
        }
        second_response = MagicMock()
        second_response.status_code = 200
        second_response.json.return_value = {
            "count": 3,
            "items": [
                {
                    "id": 2,
                    "navn": "Test Company 2",
                    "revisionsfirma": "Test Audit",
                    "virksomhedsnavn": "Test Business",
                    "cvr": "12345679",
                    "email": "test2@example.com",
                    "regnskabsår": 2023,
                    "u1_udfyldt": True,
                    "udbytte": "200000.00",
                    "noter": "Test notes",
                    "by": "Copenhagen",
                    "dato": "2023-01-02",
                    "underskriftsberettiget": "Test Person",
                    "oprettet": "2023-01-02T12:00:00",
                    "oprettet_af_cpr": "1234567891",
                    "oprettet_af_cvr": "12345679",
                },
            ],
        }
        third_response = MagicMock()
        third_response.status_code = 200
        third_response.json.return_value = {
            "count": 3,
            "items": [
                {
                    "id": 3,
                    "navn": "Test Company 3",
                    "revisionsfirma": "Test Audit",
                    "virksomhedsnavn": "Test Business",
                    "cvr": "12345680",
                    "email": "test3@example.com",
                    "regnskabsår": 2023,
                    "u1_udfyldt": True,
                    "udbytte": "300000.00",
                    "noter": "Test notes",
                    "by": "Copenhagen",
                    "dato": "2023-01-03",
                    "underskriftsberettiget": "Test Person",
                    "oprettet": "2023-01-03T12:00:00",
                    "oprettet_af_cpr": "1234567892",
                    "oprettet_af_cvr": "12345680",
                },
            ],
        }

        mock_get.side_effect = [first_response, second_response, third_response]

        entries = get_akap_u1a_entries(
            self.host, self.auth_token, limit=1, fetch_all=True
        )

        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].id, 1)
        self.assertEqual(entries[1].id, 2)
        self.assertEqual(entries[2].id, 3)

        # Verify all pages were requested
        mock_get.assert_any_call(
            self.host + URL_U1A_LIST,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 1, "offset": 0},
        )
        mock_get.assert_any_call(
            self.host + URL_U1A_LIST,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 1, "offset": 1},
        )
        mock_get.assert_any_call(
            self.host + URL_U1A_LIST,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 1, "offset": 2},
        )

    @patch("bf.akap.requests.get")
    def test_get_akap_u1a_entries_invalid_response(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request"
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            get_akap_u1a_entries(self.host, self.auth_token)
        self.assertIn(
            "AKAP udbytte API did not respond with HTTP 200", str(context.exception)
        )

    @patch("bf.akap.requests.get")
    def test_get_akap_u1a_items_full_coverage(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 1,
            "items": [
                {
                    "id": 1,
                    "u1a": 1,
                    "cpr_cvr_tin": "1234567890",
                    "navn": "Test Name",
                    "adresse": "Test Address",
                    "postnummer": "1000",
                    "by": "Copenhagen",
                    "land": "Denmark",
                    "udbytte": "5000.00",
                    "oprettet": "2023-01-01T12:00:00",
                }
            ],
        }
        mock_get.return_value = mock_response

        # Test with all parameters
        items = get_akap_u1a_items(
            self.host, self.auth_token, u1a_id=1, year=2023, cpr="1234567890"
        )
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], AKAPU1AItem)
        mock_get.assert_called_once_with(
            self.host + URL_U1A_ITEMS,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={
                "limit": 50,
                "offset": 0,
                "u1a": 1,
                "year": 2023,
                "cpr_cvr_tin": "1234567890",
            },
        )

        # Test with partial parameters (only year)
        mock_get.reset_mock()
        items = get_akap_u1a_items(self.host, self.auth_token, year=2023)
        mock_get.assert_called_once_with(
            self.host + URL_U1A_ITEMS,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 50, "offset": 0, "year": 2023},
        )

        mock_get.reset_mock()
        items = get_akap_u1a_items(self.host, self.auth_token)
        mock_get.assert_called_once_with(
            self.host + URL_U1A_ITEMS,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 50, "offset": 0},
        )

    @patch("bf.akap.requests.get")
    def test_get_akap_u1a_items_unique_cprs(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 1,
            "items": ["1234567890"],
        }
        mock_get.return_value = mock_response

        unique_cprs = get_akap_u1a_items_unique_cprs(self.host, self.auth_token)
        self.assertEqual(len(unique_cprs), 1)
        self.assertEqual(unique_cprs[0], "1234567890")

    @patch("bf.akap.requests.get")
    @patch("bf.akap.logger")
    def test_get_akap_u1a_items_non_200_response(
        self, mock_logger: MagicMock, mock_get: MagicMock
    ):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            get_akap_u1a_items(self.host, self.auth_token)

        mock_logger.error.assert_called_once_with("Internal Server Error")
        self.assertIn(
            "AKAP udbytte API did not respond with HTTP 200", str(context.exception)
        )
        mock_get.assert_called_once_with(
            self.host + URL_U1A_ITEMS,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            params={"limit": 50, "offset": 0},
        )

    def test_model_validation_error(self):
        with self.assertRaises(ValidationError):
            AKAPU1A(
                id=1,
                navn="Test",
                revisionsfirma="Test",
                virksomhedsnavn="Test",
                cvr="123",
                email="not-an-email",
                regnskabsår="not-a-year",
                udbytte="not-a-decimal",
                dato="not-a-date",
                oprettet="not-a-datetime",
                oprettet_af_cpr="123",
            )

    def test_str_methods(self):
        u1a = AKAPU1A(
            id=1,
            navn="Test Company",
            revisionsfirma="Test Audit",
            virksomhedsnavn="Test Business",
            cvr="12345678",
            email="test@example.com",
            regnskabsår=2023,
            u1_udfyldt=True,
            udbytte=Decimal("100000.00"),
            noter="Some notes",
            by="Copenhagen",
            dato=date(2023, 1, 1),
            underskriftsberettiget="Authorized Person",
            oprettet=datetime(2023, 1, 1, 12, 0, 0),
            oprettet_af_cpr="1234567890",
            oprettet_af_cvr="87654321",
        )
        self.assertEqual(str(u1a), "Test Company - 12345678 - test@example.com - 2023")

        item = AKAPU1AItem(
            id=1,
            u1a=u1a.id,
            cpr_cvr_tin="1234567890",
            navn="Test Name",
            adresse="Test Address",
            postnummer="1000",
            by="Copenhagen",
            land="Denmark",
            udbytte=Decimal("5000.00"),
            oprettet=datetime(2023, 1, 1, 12, 0, 0),
        )
        self.assertEqual(
            str(item),
            "Test Name - 1234567890 - Test Address, 1000 Copenhagen - Denmark",
        )
