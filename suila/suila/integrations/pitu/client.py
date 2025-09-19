# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime
from typing import List, Set

from django.conf import settings
from requests import ReadTimeout, Session


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
        person_info_service=None,
        person_subscription_service=None,
        company_info_service=None,
    ):
        self.person_info_service = person_info_service
        self.person_subscription_service = person_subscription_service
        self.company_info_service = company_info_service
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

    def get(self, path, params=None, service=None):
        if params is None:
            params = {}
        if service is None:
            service = self.person_info_service
        r = self.session.get(
            self.base_url + path,
            params=params,
            timeout=self.timeout,
            headers={"Uxp-Service": service},
        )
        r.raise_for_status()
        return r.json()

    def close(self):
        self.session.close()

    def get_person_info(self, cpr: str):
        return self.get(f"/personLookup/1/cpr/{cpr}", service=self.person_info_service)

    def get_company_info(self, cvr: int | str):
        return self.get(f"/{cvr}", service=self.company_info_service)

    def get_subscription_results(
        self, last_update_time: datetime | None = None
    ) -> Set[str]:
        subscription_id: str = "suilaCprEvent"
        service = self.person_subscription_service
        page_size = 100
        params = {
            "pageSize": page_size,
            "subscription": subscription_id,
        }
        if last_update_time is not None:
            params["timestamp.GTE"] = last_update_time.isoformat()

        cpr_list: List[str] = []
        page = 1
        while True:
            page_params = params.copy()
            page_params["page"] = page
            retries = 5
            exception: BaseException | None = None
            for retry in range(retries):
                try:
                    results = self.get(
                        "/findCprDataEvent/fetchEvents", page_params, service
                    )
                    exception = None
                    break
                except ReadTimeout as e:
                    exception = e

            if exception is not None:
                raise exception
            batch_cpr_list: List[str] | None = results.get("results")
            if batch_cpr_list is None:
                raise Exception(f"Unexpected None in cprList: {results}")
            cpr_list.extend(batch_cpr_list)
            if len(batch_cpr_list) < page_size:
                break
            if page > 10000:
                raise Exception(
                    f"Looped for more than 10000 pages of results. "
                    f"Something is wrong. Collected {len(set(cpr_list))} unique "
                    f"cprs out of {len(cpr_list)} total returned cprs"
                )
            page += 1
        return set(cpr_list)
