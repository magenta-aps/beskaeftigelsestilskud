# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from unittest.mock import MagicMock, patch

from django.test import TestCase
from requests import HTTPError
from requests.exceptions import ConnectTimeout, ReadTimeout, SSLError, TooManyRedirects
from tenQ.client import ClientException


class MetricsTest(TestCase):
    def test_health_check_storage(self):
        resp = self.client.get("/metrics/health/storage")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")

    @patch("tempfile.NamedTemporaryFile")
    def test_health_check_storage_value_error(self, mock_tempfile):
        mock_tempfile.read = MagicMock(return_value=b"invalid_content")

        resp = self.client.get("/metrics/health/storage")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.content, b"ERROR")

    def test_health_check_database(self):
        resp = self.client.get("/metrics/health/database")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")

    @patch("django.db.connection.ensure_connection")
    def test_health_check_database_exception(self, mock_ensure_connection):
        mock_ensure_connection.side_effect = Exception("Database connection failed")

        resp = self.client.get("/metrics/health/database")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.content, b"ERROR")

    @patch("metrics.views.list_prisme_folder")
    def test_health_check_sftp(self, mock_list_prisme_folder):
        resp = self.client.get("/metrics/health/sftp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")

    @patch("metrics.views.list_prisme_folder")
    def test_health_check_sftp_exception(self, mock_list_prisme_folder):
        mock_list_prisme_folder.side_effect = ClientException("Uh-oh!")

        resp = self.client.get("/metrics/health/sftp")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.content, b"ERROR")

    @patch("metrics.views.EskatClient.get_tax_scopes")
    def test_health_check_eskat(self, mock_get_tax_scopes):
        mock_get_tax_scopes.return_value = {"foo": "bar"}
        resp = self.client.get("/metrics/health/eskat")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")

    @patch("metrics.views.EskatClient.get_tax_scopes")
    def test_health_check_eskat_exception(self, mock_get_tax_scopes):
        for exception_class in (
            HTTPError,
            SSLError,
            ConnectTimeout,
            ReadTimeout,
            TooManyRedirects,
        ):
            mock_get_tax_scopes.side_effect = exception_class("Uh-oh!")
            resp = self.client.get("/metrics/health/eskat")
            self.assertEqual(resp.status_code, 500)
            self.assertEqual(resp.content, b"ERROR")
