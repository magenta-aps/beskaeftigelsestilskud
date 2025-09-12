# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from threading import current_thread
from typing import Any, Dict, Iterable, List

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from requests import Response, Session
from requests_ntlm import HttpNtlmAuth

from suila.integrations.eskat.load import (
    AnnualIncomeHandler,
    ExpectedIncomeHandler,
    MonthlyIncomeHandler,
    TaxInformationHandler,
)
from suila.integrations.eskat.responses.data_models import (
    AnnualIncome,
    ExpectedIncome,
    MonthlyIncome,
    TaxInformation,
)

logger = logging.getLogger(__name__)


class EskatClient:
    def __init__(
        self, base_url: str, username: str, password: str, verify: bool | str = True
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify = verify
        self.sessions: Dict[str, Session] = {}

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

    """
    def get_many_parallel(
        self,
        paths: Iterable[str],
        threads: int = 8) -> Iterable[Dict[str, Any]]:
        # Parallel implementation.
        # Henter data, og fylder modtagerens buffer, ret hurtigt
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(self.get, path) for path in paths]
            for future in as_completed(futures):
                yield future.result()
            self.sessions = {}
    """

    def get_many(self, paths: Iterable[str]) -> Iterable[Dict[str, Any]]:
        # Sekventiel implementation. Henter langsommere, så modtageren kan følge med
        for path in paths:
            yield self.get(path)
        self.sessions = {}

    def get_chunked(self, path: str, chunk_size: int = 20) -> Iterable[Dict[str, Any]]:
        chunk: int = 1
        first_response = self.get(path + f"?chunk={chunk}&chunkSize={chunk_size}")
        total_chunks = first_response["totalChunks"]
        logger.info(f"total eskat chunks: {total_chunks} of size {chunk_size}")
        yield first_response
        if total_chunks > 1:
            remaining_paths = [
                path + f"?chunk={chunk}&chunkSize={chunk_size}"
                for chunk in range(2, total_chunks + 1)
            ]
            for response in self.get_many(remaining_paths):
                yield response

    @staticmethod
    def unpack(responses: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
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
        if not settings.ESKAT_BASE_URL:  # type: ignore[misc]
            raise ImproperlyConfigured(
                "ESKAT_BASE_URL is not set - cannot initialize eskat client"
            )

        return EskatClient(
            settings.ESKAT_BASE_URL,  # type: ignore[misc]
            settings.ESKAT_USERNAME,  # type: ignore[misc]
            settings.ESKAT_PASSWORD,  # type: ignore[misc]
            settings.ESKAT_VERIFY,  # type: ignore[misc]
        )

    def get_annual_income(
        self,
        year: int,
        cpr: str | None = None,
        chunk_size: int = 20,
    ) -> Iterable[AnnualIncome]:
        if cpr is None:
            responses = self.get_chunked(
                f"/api/annualincome/get/chunks/all/{year}", chunk_size
            )
        else:
            responses = [self.get(f"/api/annualincome/get/{cpr}/{year}")]
        for item in self.unpack(responses):
            yield AnnualIncomeHandler.from_api_dict(item)

    def get_expected_income(
        self,
        year: int,
        cpr: str | None = None,
        chunk_size: int = 20,
    ) -> Iterable[ExpectedIncome]:
        if cpr is None:
            responses = self.get_chunked(
                f"/api/expectedincome/get/chunks/all/{year}", chunk_size
            )
        else:
            responses = [self.get(f"/api/expectedincome/get/{cpr}/{year}")]
        for item in self.unpack(responses):
            yield ExpectedIncomeHandler.from_api_dict(item)

    def get_monthly_income(
        self,
        year: int,
        month_from: int | None = None,
        month_to: int | None = None,
        cpr: str | None = None,
        chunk_size: int = 20,
    ) -> Iterable[MonthlyIncome]:
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
            responses = self.get_chunked(url, chunk_size)
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
        for item in self.unpack(responses):
            yield MonthlyIncomeHandler.from_api_dict(item)

    def get_tax_information(
        self,
        year: int,
        cpr: str | None = None,
        chunk_size: int = 20,
    ) -> Iterable[TaxInformation]:
        if cpr is None:
            responses = self.get_chunked(
                f"/api/taxinformation/get/chunks/all/{year}",
                chunk_size,
            )
        else:
            responses = [self.get(f"/api/taxinformation/get/{cpr}/{year}")]
        for item in self.unpack(responses):
            yield TaxInformationHandler.from_api_dict(item)

    def get_tax_scopes(self) -> List[str]:
        return self.get("/api/taxinformation/get/taxscopes")["data"]
