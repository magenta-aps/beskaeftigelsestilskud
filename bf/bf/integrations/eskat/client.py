# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import Any, Dict

import requests
from django.conf import settings
from requests import Response
from requests_ntlm import HttpNtlmAuth


class EskatClient:
    def __init__(
        self, base_url: str, username: str, password: str, verify: bool | str = True
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify = verify
        self.session = requests.Session()
        self.session.auth = HttpNtlmAuth(username, password)
        self.session.verify = verify

    def get(self, path: str) -> Dict[str, Any]:
        response: Response = self.session.get(
            self.base_url + path,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def from_settings() -> "EskatClient":
        return EskatClient(
            settings.ESKAT_BASE_URL,  # type: ignore[misc]
            settings.ESKAT_USERNAME,  # type: ignore[misc]
            settings.ESKAT_PASSWORD,  # type: ignore[misc]
            settings.ESKAT_VERIFY,  # type: ignore[misc]
        )
