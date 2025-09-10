# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import MagicMock

from django.test import TestCase
from django.test.utils import override_settings

from suila.integrations.pitu.client import PituClient

pitu_test_settings = {
    "certificate": "test_cert",
    "private_key": "test_key",
    "root_ca": "test_ca",
    "client_header": "test_header",
    "base_url": "test_url",
    "person_info_service": "test_service",
    "company_info_service": "test_cvr_service",
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
        self.assertEqual(self.pitu_client.person_info_service, "test_service")
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

    def test_get_subscription_results(self):
        cprs = [str(x).zfill(10) for x in range(1, 250)]
        envelope_prototype = {
            "path": None,
            "terms": "https://doc.test.data.gl/terms",
            "requestTimestamp": None,
            "responseTimestamp": None,
            "newestResultTimestamp": "2025-09-09T16:01:00Z",
            "username": None,
            "page": 0,
            "pageSize": 100,
            "results": [],
        }
        envelope_list = []
        for page, offset in enumerate(range(0, 300, 100), 1):
            sub_cprs = cprs[offset : offset + 100]
            envelope = envelope_prototype.copy()
            envelope["results"] = sub_cprs
            envelope["page"] = page
            envelope_list.append(envelope)
        response_mock.json.side_effect = envelope_list
        results = self.pitu_client.get_subscription_results()
        self.assertEqual(results, set(cprs))
