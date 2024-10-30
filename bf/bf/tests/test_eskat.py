# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import json
import re
from decimal import Decimal
from math import ceil
from sys import stdout
from unittest.mock import patch
from urllib.parse import parse_qs

from django.test import TestCase, override_settings
from requests import HTTPError, Response

from bf.integrations.eskat.client import EskatClient
from bf.integrations.eskat.load import MonthlyIncomeHandler
from bf.integrations.eskat.responses.data_models import MonthlyIncome
from bf.models import MonthlyAIncomeReport, MonthlyBIncomeReport, PersonMonth


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

    data = [
        {
            "cpr": "1234",
            "year": 2024,
            "month": m,
            "salaryIncome": m * 1000,
            "catchsaleIncome": 0,
            "publicAssistanceIncome": 0,
            "alimonyIncome": 0,
            "disGisIncome": 0,
            "retirementPensionIncome": 0,
            "disabilityPensionIncome": 0,
            "ignoredBenefitsIncome": 0,
            "employerPaidGLPensionIncome": 0,
            "foreignPensionIncome": 0,
            "civilServantPensionIncome": 0,
            "otherPensionIncome": 0,
        }
        for m in range(1, 13)
    ] + [
        {
            "cpr": "5678",
            "year": 2024,
            "month": m,
            "salaryIncome": m * 500,
            "catchsaleIncome": 0,
            "publicAssistanceIncome": 0,
            "alimonyIncome": 0,
            "disGisIncome": 0,
            "retirementPensionIncome": 0,
            "disabilityPensionIncome": 0,
            "ignoredBenefitsIncome": 0,
            "employerPaidGLPensionIncome": 0,
            "foreignPensionIncome": 0,
            "civilServantPensionIncome": 0,
            "otherPensionIncome": 0,
        }
        for m in range(1, 13)
    ]

    @staticmethod
    def cast_int(i):
        if i is None:
            return None
        return int(i)

    def monthly_income_testdata(self, url):
        match = re.match(
            r"https://eskattest/eTaxCommonDataApi/api/monthlyincome/get"
            r"/(?P<type>chunks/all|all|\d+)"
            r"/(?P<year>\d+)"
            r"(?:/(?P<month1>\d+)(?:/(?P<month2>\d+))?)?"
            r"(?:\?(?P<params>.*))?",
            url,
        )
        t = match.group("type")
        year = self.cast_int(match.group("year"))
        month1 = self.cast_int(match.group("month1"))
        month2 = self.cast_int(match.group("month2"))
        params = parse_qs(match.group("params")) if match.group("params") else {}
        chunk = int(params.get("chunk", [1])[0])
        chunk_size = int(params.get("chunkSize", [20])[0])
        items = []
        if t in ("all", "chunks/all"):
            items = filter(lambda item: item["year"] == year, self.data)
            if month1 and month2:
                items = filter(lambda item: month1 <= item["month"] <= month2, items)
            elif month1:
                items = filter(lambda item: month1 == item["month"], items)
        elif t.isdigit():
            items = filter(
                lambda item: item["year"] == year and item["cpr"] == t, self.data
            )
            if month1:
                items = filter(lambda item: month1 == item["month"], items)
        items = list(items)
        total_items = len(items)
        if t == "chunks/all":
            items = items[(chunk - 1) * chunk_size : (chunk) * chunk_size]

        return self._response(
            200,
            {
                "data": items,
                "message": "string",
                "chunk": chunk,
                "chunkSize": chunk_size,
                "totalChunks": ceil(total_items / chunk_size),
                "totalRecordsInChunks": total_items,
            },
        )

    def test_get_monthly_income_by_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024)
            self.assertEqual(len(data), 24)
            for m in range(0, 12):
                self.assertEqual(data[m].cpr, "1234")
                self.assertEqual(data[m].month, m + 1)
            for m in range(12, 24):
                self.assertEqual(data[m].cpr, "5678")
                self.assertEqual(data[m].month, m - 11)

    def test_get_monthly_income_by_year_month(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024, 1)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0].month, 1)
            self.assertEqual(data[0].cpr, "1234")
            self.assertEqual(data[1].month, 1)
            self.assertEqual(data[1].cpr, "5678")

    def test_get_monthly_income_by_year_monthrange(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024, 1, 6)
            self.assertEqual(len(data), 12)
            for m in range(0, 6):
                self.assertEqual(data[m].month, m + 1)
                self.assertEqual(data[m].cpr, "1234")
            for m in range(6, 12):
                self.assertEqual(data[m].month, m - 5)
                self.assertEqual(data[m].cpr, "5678")

    def test_get_monthly_income_by_cpr_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024, cpr="1234")
            self.assertEqual(len(data), 12)
            for m in range(0, 12):
                self.assertEqual(data[m].cpr, "1234")
                self.assertEqual(data[m].month, m + 1)

    def test_get_monthly_income_by_cpr_year_month(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024, 1, cpr="1234")
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].month, 1)
            self.assertEqual(data[0].cpr, "1234")

    def test_get_monthly_income_by_cpr_year_month_range(self):
        client = EskatClient.from_settings()
        with patch.object(
            client.session, "get", side_effect=self.monthly_income_testdata
        ):
            data = client.get_monthly_income(2024, 1, 6, cpr="1234")
            self.assertEqual(len(data), 6)
            for m in range(0, 6):
                self.assertEqual(data[m].month, m + 1)
                self.assertEqual(data[m].cpr, "1234")


class LoadHandler(TestCase):
    def test_monthly_income_load(self):
        MonthlyIncomeHandler.create_or_update_objects(
            2024,
            [
                MonthlyIncome(
                    "1234",
                    2024,
                    1,
                    salary_income=25000.00,
                    foreign_pension_income=1000.00,
                )
            ],
            stdout,
        )
        self.assertEqual(
            PersonMonth.objects.filter(person_year__year__year=2024, month=1).count(), 1
        )
        self.assertEqual(
            MonthlyAIncomeReport.objects.filter(year=2024, month=1).count(), 1
        )
        self.assertEqual(
            MonthlyBIncomeReport.objects.filter(year=2024, month=1).count(), 1
        )
        self.assertEqual(
            MonthlyAIncomeReport.objects.filter(year=2024, month=1).first().amount,
            Decimal(25000.00),
        )
        self.assertEqual(
            MonthlyBIncomeReport.objects.filter(year=2024, month=1).first().amount,
            Decimal(1000.00),
        )
