# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor, wait
from threading import current_thread
from typing import Any, Dict, Iterable, List

import requests
from django.conf import settings
from requests import Response
from requests_ntlm import HttpNtlmAuth

from bf.integrations.eskat.load import ExpectedIncomeHandler, MonthlyIncomeHandler
from bf.integrations.eskat.responses.data_models import ExpectedIncome, MonthlyIncome


class EskatClient:
    def __init__(
        self, base_url: str, username: str, password: str, verify: bool | str = True
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify = verify
        self.sessions = {}

    def get_session(self):
        thread_name = current_thread().name
        if thread_name not in self.sessions:
            session = requests.Session()
            session.auth = HttpNtlmAuth(self.username, self.password)
            session.verify = self.verify
            self.sessions[thread_name] = session
        return self.sessions[thread_name]

    def get(self, path: str) -> Dict[str, Any]:
        response: Response = self.get_session().get(self.base_url + path)
        response.raise_for_status()
        return response.json()

    def get_many(self, paths: Iterable[str], threads: int = 8) -> List[Dict[str, Any]]:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(self.get, path) for path in paths]
            wait(futures)
            results = [future.result() for future in futures]
            self.sessions = {}
            return results

    def get_chunked(self, path: str, chunk_size: int = 20) -> List[Dict[str, Any]]:
        chunk: int = 1
        first_response = self.get(path + f"?chunk={chunk}&chunkSize={chunk_size}")
        total_chunks = first_response["totalChunks"]
        responses = [first_response]
        if total_chunks > 1:
            remaining_paths = [
                path + f"?chunk={chunk}&chunkSize={chunk_size}"
                for chunk in range(2, total_chunks + 1)
            ]
            responses += self.get_many(remaining_paths)
        return responses

    @staticmethod
    def unpack(responses: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        for response in responses:
            if response is not None:
                data = response["data"]
                if data is not None:
                    if type(data) is list:
                        for item in data:
                            yield item
                    elif type(data) is dict:
                        yield data

    @staticmethod
    def from_settings() -> "EskatClient":
        return EskatClient(
            settings.ESKAT_BASE_URL,  # type: ignore[misc]
            settings.ESKAT_USERNAME,  # type: ignore[misc]
            settings.ESKAT_PASSWORD,  # type: ignore[misc]
            settings.ESKAT_VERIFY,  # type: ignore[misc]
        )

    def get_expected_income(
        self,
        year: int | None = None,
        cpr: str | None = None,
    ) -> List[ExpectedIncome]:
        if year is None:
            if cpr is None:
                raise ValueError("Must specify either year or cpr (or both)")
            responses = [self.get(f"/api/expectedincome/get/{cpr}")]
        else:
            if cpr is None:
                responses = self.get_chunked(
                    f"/api/expectedincome/get/chunks/all/{year}"
                )
            else:
                responses = [self.get(f"/api/expectedincome/get/{cpr}/{year}")]
        return [
            ExpectedIncomeHandler.from_api_dict(item) for item in self.unpack(responses)
        ]

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
