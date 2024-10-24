# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from requests import HTTPError, Response

from bf.integrations.eskat.client import EskatClient


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class EskatTest(TestCase):

    @staticmethod
    def _response(status_code: int, content: str | dict):
        if isinstance(content, dict):
            content = json.dumps(content)
        response = Response()
        response.status_code = status_code
        response._content = content.encode("utf-8")
        return response

    def test_from_settings(self):
        client = EskatClient.from_settings()
        self.assertEqual(client.base_url, "https://eskattest/eTaxCommonDataApi")
        self.assertEqual(client.username, "testuser")
        self.assertEqual(client.password, "testpass")

    def test_get(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session,
            "get",
            return_value=self._response(200, {"data": "foobar"}),
        ) as mock_get:
            response = client.get("/api/test")
            mock_get.assert_called_with(
                "https://eskattest/eTaxCommonDataApi/api/test",
            )
            self.assertEqual(response, {"data": "foobar"})

    def test_get_401(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session,
            "get",
            return_value=self._response(401, "You shall not pass"),
        ):
            with self.assertRaises(HTTPError) as error:
                client.get("/api/test")
                self.assertEqual(error.exception.response.status_code, 401)
