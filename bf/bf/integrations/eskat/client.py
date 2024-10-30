# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, Iterable, List

import requests
from django.conf import settings
from requests import Response
from requests_ntlm import HttpNtlmAuth

from bf.integrations.eskat.load import MonthlyIncomeHandler
from bf.integrations.eskat.responses.data_models import MonthlyIncome


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

    def get_many(self, paths: Iterable[str], threads: int = 8) -> List[Dict[str, Any]]:
        executor = ThreadPoolExecutor(max_workers=threads)
        futures = [executor.submit(self.get, path) for path in paths]
        wait(futures)
        return [future.result() for future in futures]

    def get_chunked(self, path: str, chunk_size: int = 10) -> List[Dict[str, Any]]:
        chunk: int = 1
        first_response = self.get(path + f"?chunk={chunk}&chunkSize={chunk_size}")
        total_chunks = first_response["totalChunks"]
        responses = [first_response]
        print(first_response)
        if total_chunks > 1:
            remaining_paths = [
                path + f"?chunk={chunk}&chunkSize={chunk_size}"
                for chunk in range(2, total_chunks + 1)
            ]
            print(remaining_paths)
            responses += self.get_many(remaining_paths)
        return responses

    @staticmethod
    def unpack(responses: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        for response in responses:
            for item in response["data"]:
                yield item

    @staticmethod
    def from_settings() -> "EskatClient":
        return EskatClient(
            settings.ESKAT_BASE_URL,  # type: ignore[misc]
            settings.ESKAT_USERNAME,  # type: ignore[misc]
            settings.ESKAT_PASSWORD,  # type: ignore[misc]
            settings.ESKAT_VERIFY,  # type: ignore[misc]
        )

    def get_monthly_income(
        self,
        year: int,
        month_from: int | None = None,
        month_to: int | None = None,
        cpr: str | None = None,
    ) -> List[MonthlyIncome]:
        if month_from == month_to:
            month_to = None
        if cpr is None:
            if month_from is None:
                url = f"/api/monthlyincome/get/chunks/all/{year}"
            elif month_to is None:
                url = f"/api/monthlyincome/get/chunks/all/{year}/{month_from}"
            else:
                url = (
                    f"/api/monthlyincome/get/chunks/all/{year}/"
                    f"{min(month_from, month_to)}/{max(month_from, month_to)}"
                )
            responses = self.get_chunked(url)
        else:
            if month_from is None:
                urls = [f"/api/monthlyincome/get/{cpr}/{year}"]
            elif month_to is None:
                urls = [f"/api/monthlyincome/get/{cpr}/{year}/{month_from}"]
            else:
                urls = [
                    f"/api/monthlyincome/get/{cpr}/{year}/{month}"
                    for month in range(
                        min(month_from, month_to), max(month_from, month_to) + 1
                    )
                ]
            responses = self.get_many(urls)
        return [
            MonthlyIncomeHandler.from_api_dict(item) for item in self.unpack(responses)
        ]
