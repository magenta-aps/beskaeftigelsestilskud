# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import MagicMock

from common.pitu import PituClient
from django.test import TestCase
from django.test.utils import override_settings

pitu_test_settings = {
    "certificate": "test_cert",
    "private_key": "test_key",
    "root_ca": "test_ca",
    "client_header": "test_header",
    "base_url": "test_url",
    "service": "test_service",
}

response_mock = MagicMock()
response_mock.json.return_value = {"foo": "bar"}

session_mock = MagicMock()
session_mock.get.return_value = response_mock


@override_settings(PITU=pitu_test_settings)
class PituTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pitu_client = PituClient.from_settings()
        cls.pitu_client.session = session_mock
        cls.pitu_client._session = session_mock

    def test_pitu_client(self):
        self.assertEqual(self.pitu_client.service, "test_service")
        self.assertEqual(self.pitu_client.cert, ("test_cert", "test_key"))
        self.assertEqual(self.pitu_client.root_ca, "test_ca")
        self.assertEqual(self.pitu_client.base_url, "test_url")
        self.assertEqual(self.pitu_client.timeout, 60)

    def test_close_pitu_client(self):
        self.assertFalse(self.pitu_client.session.close.called)
        self.pitu_client.close()
        self.assertTrue(self.pitu_client.session.close.called)

    def test_get_request(self):
        json_response = self.pitu_client.get("/foo/bar")
        self.assertTrue(self.pitu_client.session.get.called)
        self.assertEqual(json_response["foo"], "bar")

    def test_get_person_info(self):
        json_response = self.pitu_client.get_person_info("0101011234")
        self.assertTrue(self.pitu_client.session.get.called)
        self.assertEqual(json_response["foo"], "bar")
