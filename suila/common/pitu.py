# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from requests import Session


class PituClient:
    combined_service_page_size = 400

    def __init__(
        self,
        client_header=None,
        certificate=None,
        private_key=None,
        base_url=None,
        root_ca=True,
        timeout=60,
        service=None,
    ):
        self.service = service
        self.client_header = client_header
        self.cert = (certificate, private_key)
        self.root_ca = root_ca
        self.base_url = base_url
        self.timeout = timeout
        self.session = Session()
        self.session.cert = self.cert
        self.session.verify = self.root_ca
        self.session.headers.update({"Uxp-Client": client_header})

    @classmethod
    def from_settings(cls):
        return cls(**settings.PITU)

    def get(self, path, params={}):
        r = self.session.get(
            self.base_url + path,
            params=params,
            timeout=self.timeout,
            headers={"Uxp-Service": self.service},
        )
        r.raise_for_status()
        return r.json()

    def close(self):
        self.session.close()

    def get_person_info(self, cpr):
        return self.get(f"/personLookup/1/cpr/{cpr}")
