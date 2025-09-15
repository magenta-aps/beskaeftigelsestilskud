# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime
from unittest.mock import MagicMock, call

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


@override_settings(PITU=pitu_test_settings)
class PituTest(TestCase):

    def setUp(self):
        super().setUp()
        self.response_mock = MagicMock()
        self.session_mock = MagicMock()
        self.session_mock.get.return_value = self.response_mock
        self.pitu_client = PituClient.from_settings()
        self.pitu_client.session = self.session_mock
        self.pitu_client._session = self.session_mock
        self.response_mock.json.side_effect = None

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
        self.response_mock.json.return_value = {"foo": "bar"}
        json_response = self.pitu_client.get("/foo/bar")
        self.assertTrue(self.pitu_client.session.get.called)
        self.assertEqual(json_response["foo"], "bar")

    def test_get_person_info(self):
        self.response_mock.json.return_value = {"foo": "bar"}
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
        self.response_mock.json.side_effect = envelope_list.copy()
        results = self.pitu_client.get_subscription_results()
        self.assertEqual(results, set(cprs))
        self.session_mock.get.assert_has_calls(
            [
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 1,
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 2,
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 3,
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
            ],
            any_order=True,
        )

    def test_get_subscription_results_timed(self):
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
        self.response_mock.json.side_effect = envelope_list.copy()
        now = datetime.now()
        results = self.pitu_client.get_subscription_results(now)
        self.assertEqual(results, set(cprs))
        self.session_mock.get.assert_has_calls(
            [
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 1,
                        "timestamp.GTE": now.isoformat(),
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 2,
                        "timestamp.GTE": now.isoformat(),
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
                call(
                    "test_url/findCprDataEvent/fetchEvents",
                    params={
                        "pageSize": 100,
                        "subscription": "suilaCprEvent",
                        "page": 3,
                        "timestamp.GTE": now.isoformat(),
                    },
                    timeout=60,
                    headers={"Uxp-Service": "test_service"},
                ),
            ],
            any_order=True,
        )

    def test_get_subscription_results_no_key(self):
        envelope = {
            "path": None,
            "terms": "https://doc.test.data.gl/terms",
            "requestTimestamp": None,
            "responseTimestamp": None,
            "newestResultTimestamp": "2025-09-09T16:01:00Z",
            "username": None,
            "page": 1,
            "pageSize": 100,
            # "results": [],  we test for handling when this is missing
        }
        self.response_mock.json.side_effect = [envelope]
        with self.assertRaises(Exception) as cm:
            self.pitu_client.get_subscription_results()
        exception = cm.exception
        self.assertEqual(exception.args, (f"Unexpected None in cprList: {envelope}",))

    def test_get_subscription_results_infinite(self):
        # Dafo returns no end to the cprs (maybe repeating responses?)
        # Shouldn't happen, but we guard against it anyway
        envelope = {
            "path": None,
            "terms": "https://doc.test.data.gl/terms",
            "requestTimestamp": None,
            "responseTimestamp": None,
            "newestResultTimestamp": "2025-09-09T16:01:00Z",
            "username": None,
            "page": 1,
            "pageSize": 100,
            "results": [str(x).zfill(10) for x in range(1, 101)],
        }
        self.response_mock.json.return_value = envelope
        with self.assertRaises(Exception) as cm:
            self.pitu_client.get_subscription_results()
        exception = cm.exception
        self.assertEqual(
            exception.args,
            (
                "Looped for more than 10000 pages of results. "
                "Something is wrong. "
                "Collected 100 unique cprs out of 1000100 total returned cprs",
            ),
        )
