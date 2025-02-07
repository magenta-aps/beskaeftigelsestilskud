# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import json
import re
from dataclasses import fields
from datetime import date
from decimal import Decimal
from io import StringIO, TextIOBase
from math import ceil
from sys import stdout
from threading import current_thread
from typing import Any, List
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

import requests
from django.test import TestCase, override_settings
from django.test.testcases import SimpleTestCase
from requests import HTTPError, Response

from suila.integrations.eskat.client import EskatClient
from suila.integrations.eskat.load import (
    AnnualIncomeHandler,
    ExpectedIncomeHandler,
    Handler,
    MonthlyIncomeHandler,
    TaxInformationHandler,
)
from suila.integrations.eskat.responses.data_models import (
    AnnualIncome,
    ExpectedIncome,
    MonthlyIncome,
    TaxInformation,
)
from suila.management.commands.calculate_benefit import (
    Command as CalculateBenefitCommand,
)
from suila.management.commands.estimate_income import Command as EstimateIncomeCommand
from suila.management.commands.load_eskat import Command as LoadEskatCommand
from suila.models import AnnualIncome as AnnualIncomeModel
from suila.models import (
    DataLoad,
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    TaxScope,
    Year,
)
from suila.tests.mixins import BaseEnvMixin


def make_response(status_code: int, content: str | dict):
    if isinstance(content, dict):
        content = json.dumps(content)
    response = Response()
    response.status_code = status_code
    response._content = content.encode("utf-8")
    return response


def cast_int(i):
    if i is None:
        return None
    return int(i)


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class EskatTest(TestCase):

    def test_from_settings(self):
        client = EskatClient.from_settings()
        self.assertEqual(client.base_url, "https://eskattest/eTaxCommonDataApi")
        self.assertEqual(client.username, "testuser")
        self.assertEqual(client.password, "testpass")

    def test_get_session(self):
        client = EskatClient.from_settings()

        thread_name = current_thread().name

        self.assertNotIn(thread_name, client.sessions)
        client.get_session()
        self.assertIn(thread_name, client.sessions)

        # Validate that the sessions dict is unchanged when calling the function a
        # second time
        ID = id(client.sessions)
        sessions = client.sessions
        client.get_session()
        self.assertEqual(ID, id(client.sessions))
        self.assertEqual(sessions, client.sessions)

    def test_unpack(self):
        client = EskatClient.from_settings()

        responses = [
            None,
            {"data": None},
            {"data": [1, 2]},
            {"data": {"item1": 3, "item2": 4}},
            {"data": (5, 6)},
        ]

        unpacked_responses = list(client.unpack(responses))

        self.assertIn(1, unpacked_responses)
        self.assertIn(2, unpacked_responses)
        self.assertIn(3, unpacked_responses[2].values())
        self.assertIn(4, unpacked_responses[2].values())
        self.assertNotIn(5, unpacked_responses)
        self.assertNotIn(6, unpacked_responses)

    def test_get(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session,
            "get",
            return_value=make_response(200, {"data": "foobar"}),
        ) as mock_get:
            response = client.get("/api/test")
            mock_get.assert_called_with(
                "https://eskattest/eTaxCommonDataApi/api/test",
            )
            self.assertEqual(response, {"data": "foobar"})

    def test_get_401(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session,
            "get",
            return_value=make_response(401, "You shall not pass"),
        ):
            with self.assertRaises(HTTPError) as error:
                client.get("/api/test")
                self.assertEqual(error.exception.response.status_code, 401)


class BaseTestCase(TestCase):
    class OutputWrapper(TextIOBase):

        def __init__(self, out, ending="\n"):
            self._out = out
            self.ending = ending

        def write(self, msg="", style_func=None, ending=None):
            pass

    @staticmethod
    def filter_data(items: List[dict], year: int | None, typ: str) -> List[dict]:
        if typ.isdigit():
            items = filter(lambda item: item["cpr"] == typ, items)
        if year is not None:
            items = filter(lambda item: item["year"] == year, items)
        return list(items)

    @staticmethod
    def slice_data(
        items: List[Any], typ: str, chunk: int, chunk_size: int
    ) -> List[Any]:
        if typ == "chunks/all":
            return items[(chunk - 1) * chunk_size : (chunk) * chunk_size]
        return items


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class TestAnnualIncome(BaseTestCase):

    annual_data = [
        {
            "cpr": "0000001234",
            "year": 2024,
            "salary": None,
            "public_assistance_income": None,
            "retirement_pension_income": None,
            "disability_pension_income": None,
            "ignored_benefits": None,
            "occupational_benefit": None,
            "foreign_pension_income": None,
            "subsidy_foreign_pension_income": None,
            "dis_gis_income": None,
            "other_a_income": None,
            "deposit_interest_income": None,
            "bond_interest_income": None,
            "other_interest_income": None,
            "education_support_income": None,
            "care_fee_income": None,
            "alimony_income": None,
            "foreign_dividend_income": None,
            "foreign_income": None,
            "free_journey_income": None,
            "group_life_income": None,
            "rental_income": None,
            "other_b_income": None,
            "free_board_income": None,
            "free_lodging_income": None,
            "free_housing_income": None,
            "free_phone_income": None,
            "free_car_income": None,
            "free_internet_income": None,
            "free_boat_income": None,
            "free_other_income": None,
            "pension_payment_income": None,
            "catch_sale_market_income": None,
            "catch_sale_factory_income": None,
            "account_tax_result": None,
            "account_share_business_amount": None,
            "shareholder_dividend_income": None,
        }
    ] + [
        {
            "cpr": "0000005678",
            "year": 2024,
            "salary": None,
            "public_assistance_income": None,
            "retirement_pension_income": None,
            "disability_pension_income": None,
            "ignored_benefits": None,
            "occupational_benefit": None,
            "foreign_pension_income": None,
            "subsidy_foreign_pension_income": None,
            "dis_gis_income": None,
            "other_a_income": None,
            "deposit_interest_income": None,
            "bond_interest_income": None,
            "other_interest_income": None,
            "education_support_income": None,
            "care_fee_income": None,
            "alimony_income": None,
            "foreign_dividend_income": None,
            "foreign_income": None,
            "free_journey_income": None,
            "group_life_income": None,
            "rental_income": None,
            "other_b_income": None,
            "free_board_income": None,
            "free_lodging_income": None,
            "free_housing_income": None,
            "free_phone_income": None,
            "free_car_income": None,
            "free_internet_income": None,
            "free_boat_income": None,
            "free_other_income": None,
            "pension_payment_income": None,
            "catch_sale_market_income": None,
            "catch_sale_factory_income": None,
            "account_tax_result": None,
            "account_share_business_amount": None,
            "shareholder_dividend_income": None,
        }
    ]

    def annual_income_testdata(self, url):
        match = re.match(
            r"https://eskattest/eTaxCommonDataApi/api/annualincome/get"
            r"/(?P<type>chunks/all|all|\d+)"
            r"(?:/(?P<year>\d+))?"
            r"(?:\?(?P<params>.*))?",
            url,
        )
        t = match.group("type")
        year = cast_int(match.group("year"))
        params = parse_qs(match.group("params")) if match.group("params") else {}
        chunk = int(params.get("chunk", [1])[0])
        chunk_size = int(params.get("chunkSize", [20])[0])
        items = self.filter_data(self.annual_data, year, t)
        total_items = len(items)
        items = self.slice_data(items, t, chunk, chunk_size)

        # Eskat sometimes does this, and we need to check the code that compensates
        if len(items) == 1:
            items = items[0]

        return make_response(
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

    def test_get_annual_income_by_none(self):
        client = EskatClient.from_settings()
        with self.assertRaises(ValueError):
            list(client.get_annual_income(None, None))

    def test_get_annual_income_by_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.annual_income_testdata
        ):
            data = list(client.get_annual_income(2024))
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[0].year, 2024)
            self.assertEqual(data[1].cpr, "0000005678")
            self.assertEqual(data[1].year, 2024)

    def test_get_annual_income_by_cpr(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.annual_income_testdata
        ):
            data = list(client.get_annual_income(year=None, cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].cpr, "0000001234")

    def test_get_annual_income_by_cpr_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.annual_income_testdata
        ):
            data = list(client.get_annual_income(2024, cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[0].year, 2024)

    def test_annual_income_load(self):
        AnnualIncomeHandler.create_or_update_objects(
            [
                AnnualIncome(
                    "0000001234",
                    2024,
                    salary=1234.56,
                ),
                AnnualIncome(None, 2024),  # shall be ignored
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(
            AnnualIncomeModel.objects.filter(person_year__year__year=2024).count(), 1
        )

        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(Person.objects.first().cpr, "0000001234")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(AnnualIncomeModel.objects.first().load.source, "test")

    def test_monthly_income_load_no_items(self):
        objects_before = len(AnnualIncomeModel.objects.all())
        AnnualIncomeHandler.create_or_update_objects(
            [],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        objects_after = len(AnnualIncomeModel.objects.all())
        self.assertEqual(objects_before, objects_after)


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class TestExpectedIncome(BaseTestCase):

    expected_data = [
        {
            "cpr": "0000001234",
            "year": 2024,
            "valid_from": "20240201",
            "do_expect_a_income": True,
            "capital_income": 123.45,
            "education_support_income": 0,
            "care_fee_income": 0.0,
            "alimony_income": 0.0,
            "benefits_income": 0.0,
            "other_b_income": 0.0,
            "gross_business_income": 0.0,
            "catch_sale_factory_income": 0.0,
            "catch_sale_market_income": 0.0,
        },
        {
            "cpr": "0000005678",
            "year": 2024,
            "valid_from": "20240201",
            "do_expect_a_income": True,
            "capital_income": 123.45,
            "education_support_income": 0.0,
            "care_fee_income": 0.0,
            "alimony_income": 0.0,
            "benefits_income": 0.0,
            "other_b_income": 0.0,
            "gross_business_income": 0.0,
            "catch_sale_factory_income": 0.0,
            "catch_sale_market_income": 0.0,
        },
    ]

    def expected_income_testdata(self, url):
        match = re.match(
            r"https://eskattest/eTaxCommonDataApi/api/expectedincome/get"
            r"/(?P<type>chunks/all|all|\d+)"
            r"(?:/(?P<year>\d+))?"
            r"(?:\?(?P<params>.*))?",
            url,
        )
        t = match.group("type")
        year = cast_int(match.group("year"))
        params = parse_qs(match.group("params")) if match.group("params") else {}
        chunk = int(params.get("chunk", [1])[0])
        chunk_size = int(params.get("chunkSize", [20])[0])
        items = self.filter_data(self.expected_data, year, t)
        total_items = len(items)
        items = self.slice_data(items, t, chunk, chunk_size)

        # Eskat sometimes does this, and we need to check the code that compensates
        if len(items) == 1:
            items = items[0]

        return make_response(
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

    def test_get_expected_income_by_none(self):
        client = EskatClient.from_settings()
        with self.assertRaises(ValueError):
            list(client.get_expected_income(None, None))

    def test_get_expected_income_by_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.expected_income_testdata
        ):
            data = list(client.get_expected_income(year=2024))
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[1].cpr, "0000005678")

    def test_get_expected_income_by_cpr(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.expected_income_testdata
        ):
            data = list(client.get_expected_income(cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].cpr, "0000001234")

    def test_get_expected_income_by_cpr_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.expected_income_testdata
        ):
            data = list(client.get_expected_income(year=2024, cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].cpr, "0000001234")

    def test_expected_income_load(self):
        ExpectedIncomeHandler.create_or_update_objects(
            2024,
            [
                ExpectedIncome(
                    "0000001234",
                    2024,
                    other_b_income=2000.00,
                ),
                ExpectedIncome(None, 2024),  # shall be ignored
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(
            PersonYearAssessment.objects.filter(person_year__year__year=2024).count(), 1
        )
        self.assertEqual(
            PersonYearAssessment.objects.filter(person_year__year__year=2024)
            .first()
            .other_b_income,
            Decimal(2000.00),
        )
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(Person.objects.first().cpr, "0000001234")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(PersonYearAssessment.objects.first().load.source, "test")

    def test_expected_income_load_no_items(self):

        objects_before = len(PersonYearAssessment.objects.all())
        ExpectedIncomeHandler.create_or_update_objects(
            2024,
            [],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        objects_after = len(PersonYearAssessment.objects.all())
        self.assertEqual(objects_before, objects_after)


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class TestMonthlyIncome(BaseTestCase):

    monthly_data = [
        {
            "cpr": "0000001234",
            "cvr": "123",
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
            "cpr": "0000005678",
            "cvr": "567",
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
        year = cast_int(match.group("year"))
        month1 = cast_int(match.group("month1"))
        month2 = cast_int(match.group("month2"))
        params = parse_qs(match.group("params")) if match.group("params") else {}
        chunk = int(params.get("chunk", [1])[0])
        chunk_size = int(params.get("chunkSize", [20])[0])
        items = self.filter_data(self.monthly_data, year, t)

        if t in ("all", "chunks/all") and month1 and month2:
            items = filter(lambda item: month1 <= item["month"] <= month2, items)
        elif month1:
            items = filter(lambda item: month1 == item["month"], items)
        items = list(items)
        total_items = len(items)
        items = self.slice_data(items, t, chunk, chunk_size)

        # Eskat sometimes does this, and we need to check the code that compensates
        if len(items) == 1:
            items = items[0]

        return make_response(
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
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024))
            self.assertEqual(len(data), 24)
            for m in range(0, 12):
                self.assertEqual(data[m].cpr, "0000001234")
                self.assertEqual(data[m].month, m + 1)
            for m in range(12, 24):
                self.assertEqual(data[m].cpr, "0000005678")
                self.assertEqual(data[m].month, m - 11)

    def test_get_monthly_income_by_year_month(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024, 1))
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0].month, 1)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[1].month, 1)
            self.assertEqual(data[1].cpr, "0000005678")

    def test_get_monthly_income_by_year_monthrange(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024, 1, 6))
            self.assertEqual(len(data), 12)
            for m in range(0, 6):
                self.assertEqual(data[m].month, m + 1)
                self.assertEqual(data[m].cpr, "0000001234")
            for m in range(6, 12):
                self.assertEqual(data[m].month, m - 5)
                self.assertEqual(data[m].cpr, "0000005678")

    def test_get_monthly_income_by_cpr_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024, cpr="0000001234"))
            self.assertEqual(len(data), 12)
            for m in range(0, 12):
                self.assertEqual(data[m].cpr, "0000001234")
                self.assertEqual(data[m].month, m + 1)

    def test_get_monthly_income_by_cpr_year_month(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024, 1, cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].month, 1)
            self.assertEqual(data[0].cpr, "0000001234")

    def test_get_monthly_income_by_cpr_year_month_range(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.monthly_income_testdata
        ):
            data = list(client.get_monthly_income(2024, 1, 6, cpr="0000001234"))
            self.assertEqual(len(data), 6)
            for m in range(0, 6):
                self.assertEqual(data[m].month, m + 1)
                self.assertEqual(data[m].cpr, "0000001234")

    def test_monthly_income_load(self):
        MonthlyIncomeHandler.create_or_update_objects(
            2024,
            [
                MonthlyIncome(
                    cpr="0000001234",
                    cvr="123",
                    year=2024,
                    month=1,
                    salary_income=25000.00,
                    disability_pension_income=1000.00,
                ),
                MonthlyIncome(  # shall be ignored
                    cpr=None,
                    year=2024,
                ),
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(
            PersonMonth.objects.filter(person_year__year__year=2024, month=1).count(), 1
        )
        self.assertEqual(
            MonthlyIncomeReport.objects.filter(year=2024, month=1).count(), 1
        )
        self.assertEqual(
            MonthlyIncomeReport.objects.filter(year=2024, month=1).first().employer,
            Employer.objects.get(cvr=123),
        )
        self.assertEqual(
            MonthlyIncomeReport.objects.filter(year=2024, month=1).first().a_income,
            Decimal(25000.00),
        )
        self.assertEqual(
            MonthlyIncomeReport.objects.filter(year=2024, month=1).first().b_income,
            Decimal(1000.00),
        )
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(Person.objects.first().cpr, "0000001234")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(MonthlyIncomeReport.objects.first().load.source, "test")

    def test_monthly_income_load_no_items(self):
        objects_before = len(MonthlyIncomeReport.objects.all())
        MonthlyIncomeHandler.create_or_update_objects(
            2024,
            [],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        objects_after = len(MonthlyIncomeReport.objects.all())
        self.assertEqual(objects_before, objects_after)

    def test_monthly_income_load_no_month(self):
        objects_before = len(MonthlyIncomeReport.objects.all())
        MonthlyIncomeHandler.create_or_update_objects(
            2024,
            [
                MonthlyIncome(
                    "0000001234",
                    year=2024,
                    month=None,
                    salary_income=25000.00,
                    foreign_pension_income=1000.00,
                )
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        objects_after = len(MonthlyIncomeReport.objects.all())
        self.assertEqual(objects_before, objects_after)


@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class TestTaxInformation(BaseTestCase):

    taxinfo_data = [
        {
            "cpr": "0000001234",
            "year": 2023,
            "tax_scope": "FULL",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "region_name": "",
            "district_name": "",
        },
        {
            "cpr": "0000005678",
            "year": 2023,
            "tax_scope": "FULL",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "region_name": "",
            "district_name": "",
        },
        {
            "cpr": "0000009012",
            "year": 2023,
            "tax_scope": "FULL",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "region_name": "",
            "district_name": "",
        },
        {
            "cpr": "0000001234",
            "year": 2024,
            "tax_scope": "FULL",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "regionName": "",
            "district_name": "",
        },
        {
            "cpr": "0000005678",
            "year": 2024,
            "tax_scope": "LIM",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "regionName": "",
            "district_name": "",
        },
        {
            "cpr": "bogus",
            "year": 2024,
            "tax_scope": "LIM",
            "start_date": "2024-11-01T12:39:16.986Z",
            "end_date": "2024-11-01T12:39:16.986Z",
            "tax_municipality_number": "956",
            "cpr_municipality_code": "956",
            "region_number": "",
            "regionName": "",
            "district_name": "",
        },
    ]

    def taxinfo_testdata(self, url):
        match = re.match(
            r"https://eskattest/eTaxCommonDataApi/api/taxinformation/get"
            r"/(?P<type>chunks/all|all|taxscopes|\d+)"
            r"(?:/(?P<year>\d+))?"
            r"(?:\?(?P<params>.*))?",
            url,
        )
        t = match.group("type")
        year = cast_int(match.group("year"))
        params = parse_qs(match.group("params")) if match.group("params") else {}
        chunk = int(params.get("chunk", [1])[0])
        chunk_size = int(params.get("chunkSize", [20])[0])
        if t == "taxscopes":
            items = ["FULL", "LIM"]
        else:
            items = self.filter_data(self.taxinfo_data, year, t)
        items = list(items)
        total_items = len(items)
        items = self.slice_data(items, t, chunk, chunk_size)

        # Eskat sometimes does this, and we need to check the code that compensates
        if len(items) == 1:
            items = items[0]

        return make_response(
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

    def test_get_tax_information_by_none(self):
        client = EskatClient.from_settings()
        with self.assertRaises(ValueError):
            list(client.get_tax_information(None, None))

    def test_get_tax_information_by_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.taxinfo_testdata
        ):
            data = list(client.get_tax_information(year=2023))
            self.assertEqual(len(data), 3)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[1].cpr, "0000005678")
            self.assertEqual(data[2].cpr, "0000009012")

            data = list(client.get_tax_information(year=2024))
            self.assertEqual(len(data), 3)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[1].cpr, "0000005678")
            self.assertEqual(data[2].cpr, "bogus")

    def test_get_tax_information_by_cpr(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.taxinfo_testdata
        ):
            data = list(client.get_tax_information(cpr="0000001234"))
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0].cpr, "0000001234")
            self.assertEqual(data[0].year, 2023)
            self.assertEqual(data[1].cpr, "0000001234")
            self.assertEqual(data[1].year, 2024)

    def test_get_tax_information_by_cpr_year(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.taxinfo_testdata
        ):
            data = list(client.get_tax_information(year=2024, cpr="0000001234"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0].cpr, "0000001234")

    def test_tax_information_load(self):
        TaxInformationHandler.create_or_update_objects(
            2024,
            [
                TaxInformation(
                    "0000001234",
                    2024,
                    tax_scope="FULL",
                ),
                TaxInformation(
                    None,
                    2024,
                ),
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.filter(year__year=2024).count(), 1)

        TaxInformationHandler.create_or_update_objects(
            2024,
            [
                TaxInformation(
                    "0000001234",
                    2024,
                    tax_scope="LIM",
                )
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.filter(year__year=2024).count(), 1)
        self.assertEqual(
            PersonYear.objects.filter(year__year=2024).first().tax_scope,
            TaxScope.DELVIST_SKATTEPLIGTIG,
        )

        TaxInformationHandler.create_or_update_objects(
            2024,
            [
                TaxInformation(
                    "0000001234",
                    2024,
                )
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(Person.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.first().load.source, "test")
        self.assertEqual(PersonYear.objects.filter(year__year=2024).count(), 1)
        self.assertEqual(
            PersonYear.objects.filter(year__year=2024).first().tax_scope,
            TaxScope.DELVIST_SKATTEPLIGTIG,
        )
        TaxInformationHandler.create_or_update_objects(
            2024,
            [],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertEqual(PersonYear.objects.filter(year__year=2024).count(), 1)
        self.assertEqual(
            PersonYear.objects.filter(year__year=2024).first().tax_scope,
            TaxScope.FORSVUNDET_FRA_MANDTAL,
        )

    def test_tax_information_load_skips_bogus_cpr(self):
        TaxInformationHandler.create_or_update_objects(
            2024,
            [
                TaxInformation(
                    "bogus",
                    2024,
                    tax_scope="FULL",
                )
            ],
            DataLoad.objects.create(source="test"),
            self.OutputWrapper(stdout, ending="\n"),
        )
        self.assertQuerySetEqual(Person.objects.all(), [])

    def test_get_taxscopes(self):
        client = EskatClient.from_settings()
        with patch.object(
            requests.sessions.Session, "get", side_effect=self.taxinfo_testdata
        ):
            data = client.get_tax_scopes()
            self.assertEqual(len(data), 2)
            self.assertEqual(data, ["FULL", "LIM"])


class TestHandler(SimpleTestCase):
    def test_get_field_values_exclude_kwarg_default(self):
        # Arrange
        instance = Handler()
        item = MonthlyIncome()
        # Act: call method without explicit `exclude` kwarg
        field_values = instance.get_field_values(item)
        # Assert: no fields were excluded
        self.assertListEqual(list(field_values.keys()), [f.name for f in fields(item)])


class TestLoadEskatCommand(BaseEnvMixin, TestCase):
    """Test the logic in `bf.management.commands.load_eskat.Command`"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year_2019 = Year.objects.create(year=2019, calculation_method=cls.calc)
        cls.command = LoadEskatCommand()
        # cls.command.stdout = StringIO()

    def setUp(self):
        super().setUp()
        self.person_month = self.get_or_create_person_month(
            month=1,
            import_date=date(self.year.year, 1, 1),
        )

    def test_monthly_income_retrieval_from_previous_months(self):
        """Fetching `monthlyincome` from eSkat in month N should fetch data for months
        N-4, N-3, and N-2.
        """
        test_cases: list[tuple[int, int, list[dict]]] = [
            # In January, fetch for September, October and November
            (2020, 1, [{"year": 2019, "month_from": 9, "month_to": 11}]),
            # In February, fetch for October, November and December
            (2020, 2, [{"year": 2019, "month_from": 10, "month_to": 12}]),
            # In March, fetch for November, December and January
            (
                2020,
                3,
                [
                    {"year": 2019, "month_from": 11, "month_to": 12},
                    {"year": 2020, "month_from": 1, "month_to": 1},
                ],
            ),
        ]
        for input_year, input_month, expected_args in test_cases:
            with self.subTest(year=input_year, month=input_month):
                # Arrange
                mock_client = MagicMock()
                mock_client.get_monthly_income = MagicMock()
                mock_client.get_monthly_income.return_value = [
                    MonthlyIncome(
                        cpr=self.person.cpr,
                        year=expected["year"],
                        month=m,
                        salary_income=1000,
                    )
                    for expected in expected_args
                    for m in range(expected["month_from"], expected["month_to"])
                ]
                with patch.object(
                    EskatClient, "from_settings", return_value=mock_client
                ):
                    # Act
                    self.command._handle(
                        type="monthlyincome",
                        year=input_year,
                        month=input_month,
                        cpr=None,
                        verbosity=1,
                        skew=True,
                    )
                    # Assert: API data is fetched for the expected year and month range
                    self.assertListEqual(
                        [
                            {
                                "year": call.args[0],
                                "month_from": call.kwargs["month_from"],
                                "month_to": call.kwargs["month_to"],
                            }
                            for call in mock_client.get_monthly_income.call_args_list
                        ],
                        expected_args,
                    )


class TestUpdateMixin(BaseEnvMixin):
    """Helper class for testing the behavior of data updates, as well as processing
    late data.
    """

    response_model: type | None = None
    handler: type[Handler] | None = None

    def create_or_update_objects(self, **kwargs) -> DataLoad:
        response = self.response_model(
            cpr=self.person.cpr,
            year=self.year.year,
            **kwargs,
        )
        load = DataLoad.objects.create(source="testing")
        self.handler.create_or_update_objects(*self.get_handler_args(response, load))
        return load

    def get_handler_args(self, response, load: DataLoad) -> tuple:
        return self.year.year, [response], load, StringIO()

    def estimate_income(self, month: int = 1) -> Decimal | None:
        command = EstimateIncomeCommand()
        command._handle(
            year=self.year.year,
            cpr=self.person.cpr,
            count=None,
            dry=False,
            verbosity=0,
        )
        command = CalculateBenefitCommand()
        command._handle(
            year=self.year.year,
            month=month,
            cpr=self.person.cpr,
            verbosity=0,
        )
        person_month: PersonMonth = PersonMonth.objects.get(
            person_year__year=self.year,
            person_year__person=self.person,
            month=month,
        )
        return person_month.estimated_year_result


class TestMonthlyIncomeUpdate(TestUpdateMixin, TestCase):
    """Test that subsequent updates to the same monthly income report (same person and
    month) are stored as updates to the same `MonthlyIncomeReport`, and that the
    `PersonMonth` is updated as expected.
    """

    response_model = MonthlyIncome
    handler = MonthlyIncomeHandler

    def test_subsequent_update(self):
        # Arrange: create an initial value for month 1
        load1 = self.create_or_update_objects(month=1, salary_income=1000)
        # Act: add an updated value for month 1
        load2 = self.create_or_update_objects(month=1, salary_income=2000)
        # Assert: two separate loads are recorded
        self.assertNotEqual(load1, load2)
        # Assert: there is only one `MonthlyIncomeReport` (with the latest value)
        monthly_income_reports = MonthlyIncomeReport.objects.filter(
            person_month__person_year__person=self.person,
            person_month__month=1,
        )
        self.assertQuerySetEqual(
            monthly_income_reports.values_list("month", "salary_income"),
            [(1, 2000)],
        )
        # Assert: both current and previous versions of the `MonthlyIncomeReport` are
        # kept in history, so previous amount, etc. is available.
        self.assertQuerySetEqual(
            monthly_income_reports[0]
            .history.order_by("history_date")
            .values_list("salary_income", flat=True),
            [Decimal(1000), Decimal(2000)],
        )

    def test_updated_data_affects_estimated_year_income(self):
        # Arrange: create an initial value for month 1
        self.create_or_update_objects(month=1, salary_income=20000)
        # Act: run an initial income estimation for month 1
        estimate_1 = self.estimate_income(month=1)
        # Assert: we expect 12 months of income 20,000 (= 240,000)
        self.assertEqual(estimate_1, Decimal("240000"))

        # Arrange: create an initial value for month 2, and an updated value for month 1
        self.create_or_update_objects(month=2, salary_income=10000)
        self.create_or_update_objects(month=1, salary_income=10000)
        # Act: run another income estimation (for month 2)
        estimate_2 = self.estimate_income(month=2)
        # Assert: we now expect 12 months of income 10,000 (= 120,000)
        self.assertEqual(estimate_2, Decimal("120000"))

    def test_delayed_data_affects_estimated_year_income(self):
        # Arrange: create a value for month 12
        self.create_or_update_objects(month=12, salary_income=20000)
        # Act: run an initial income estimation for month 12
        estimate_1 = self.estimate_income(month=12)
        # Assert: we expect 1 month of income 20,000, and 11 months of income 0
        self.assertEqual(estimate_1, Decimal("20000"))

        # Arrange: create a value for month 1 (= the delayed data)
        self.create_or_update_objects(month=1, salary_income=20000)
        # Act: run another income estimation (for month 12)
        estimate_2 = self.estimate_income(month=12)
        # Assert: we now expect 2 months of income 20,000 (January and December), and
        # 10 months of income 0 (the months inbetween), making a total of income 40,000.
        self.assertEqual(estimate_2, Decimal("40000"))


class TestExpectedIncomeUpdate(TestUpdateMixin, TestCase):
    """Test that subsequent updates to the same expected income report (same person and
    year) are stored as updates to the same `PersonYearAssessment`.
    """

    response_model = ExpectedIncome
    handler = ExpectedIncomeHandler

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.personyear.preferred_estimation_engine_a = "InYearExtrapolationEngine"
        cls.personyear.preferred_estimation_engine_b = "SelfReportedEngine"
        cls.personyear.save()

    def setUp(self):
        super().setUp()
        # Create an "empty" `PersonMonth` for month 1
        self.get_or_create_person_month(month=1, import_date=date(2020, 1, 1))

    def test_subsequent_update(self):
        # Arrange: create an initial value for year
        load1 = self.create_or_update_objects(capital_income=1000)
        # Act: add an updated value for year
        load2 = self.create_or_update_objects(capital_income=2000)
        # Assert: two separate loads are recorded
        self.assertNotEqual(load1, load2)
        # Assert: there is only one `PersonYearAssessment` (with the latest value)
        assessments = PersonYearAssessment.objects.filter(
            person_year__person=self.person,
            person_year__year=self.year,
        )
        self.assertQuerySetEqual(
            assessments.values_list("person_year__year__year", "capital_income"),
            [(self.year.year, 2000)],
        )
        # Assert: both current and previous versions of the `PersonYearAssessment` are
        # kept in history, so previous amount, etc. is available.
        self.assertQuerySetEqual(
            assessments[0]
            .history.order_by("history_date")
            .values_list("capital_income", flat=True),
            [Decimal(1000), Decimal(2000)],
        )

    def test_updated_data_affects_estimated_year_income(self):
        # Arrange: create an initial value for this year
        self.create_or_update_objects(capital_income=120000)
        # Act: run income estimation for month 1
        estimate_1 = self.estimate_income(month=1)
        # Assert: we expect a yearly income matching the self-reported expected income
        self.assertEqual(estimate_1, Decimal("120000"))

        # Arrange: update the previous value for this year
        self.create_or_update_objects(capital_income=60000)
        # Act: re-run income estimation for month 1
        estimate_2 = self.estimate_income(month=1)
        # Assert: we expect a yearly income matching the self-reported expected income
        self.assertEqual(estimate_2, Decimal("60000"))


class TestAnnualIncomeUpdate(TestUpdateMixin, TestCase):
    """Test that subsequent updates to the same annual income report (same person and
    year) are stored as updates to the same `AnnualIncome`.
    """

    response_model = AnnualIncome
    handler = AnnualIncomeHandler

    def setUp(self):
        super().setUp()
        # Create an "empty" `PersonMonth` for month 1 in 2020
        self.get_or_create_person_month(month=1, import_date=date(2020, 1, 1))

    def test_subsequent_update(self):
        # Arrange: create an initial value for year
        load1 = self.create_or_update_objects(salary=1000)
        # Act: add an updated value for year
        load2 = self.create_or_update_objects(salary=2000)
        # Assert: two separate loads are recorded
        self.assertNotEqual(load1, load2)
        # Assert: there is only one `AnnualIncome` (with the latest value)
        annual_incomes = AnnualIncomeModel.objects.filter(
            person_year__person=self.person,
            person_year__year=self.year,
        )
        self.assertQuerySetEqual(
            annual_incomes.values_list("person_year__year__year", "salary"),
            [(self.year.year, 2000)],
        )
        # Assert: both current and previous versions of the `AnnualIncome` are
        # kept in history, so previous amount, etc. is available.
        self.assertQuerySetEqual(
            annual_incomes[0]
            .history.order_by("history_date")
            .values_list("salary", flat=True),
            [Decimal(1000), Decimal(2000)],
        )

    def test_updated_data_affects_estimated_year_income(self):
        # Arrange: create an initial value for 2020
        self.create_or_update_objects(account_tax_result=120000)
        # Act: run income estimation for month 1 in 2020
        estimate_1 = self.estimate_income(month=1)
        # Assert: we expect a yearly income matching the self-reported expected income
        self.assertEqual(estimate_1, Decimal("120000"))

        # Arrange: create an updated value for 2020
        self.create_or_update_objects(account_tax_result=240000)
        # Act: re-run income estimation for month 1 in 2020
        estimate_2 = self.estimate_income(month=1)
        # Assert: we expect a yearly income matching the self-reported expected income
        self.assertEqual(estimate_2, Decimal("240000"))

    def get_handler_args(self, response, load: DataLoad) -> tuple:
        return [response], load, StringIO()
