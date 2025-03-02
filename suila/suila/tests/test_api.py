# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict

from bs4 import BeautifulSoup
from common.models import User
from django.test import TestCase
from ninja_extra.testing import TestClient

from suila.api import PersonAPI
from suila.api.personmonth import PersonMonthAPI
from suila.api.personyear import PersonYearAPI
from suila.models import MonthlyIncomeReport, Person, PersonMonth, PersonYear, Year


class ApiTestCase(TestCase):

    controller = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.maxDiff = 10000
        cls.client = TestClient(cls.controller)
        cls.user = User.objects.create(
            username="test", is_superuser=True, cert_subject="OU=Suila,DN=Testing"
        )
        cls.user.set_password("test")
        cls.user.save()

        cls.unprivileged_user = User.objects.create(
            username="unprivileged",
            is_superuser=False,
            cert_subject="OU=Unprivileged,DN=Testing",
        )
        cls.user.set_password("test")
        cls.user.save()

    headers_user_accepted = {
        "X-Forwarded-Tls-Client-Cert-Info": 'Subject="OU=Suila,DN=Testing";'
        'Issuer="OU=Suila,DN=Authority"'
    }

    headers_user_not_found = {
        "X-Forwarded-Tls-Client-Cert-Info": 'Subject="OU=Intruder,DN=Testing";'
        'Issuer="OU=Suila,DN=Authority"'
    }

    headers_user_unprivileged = {
        "X-Forwarded-Tls-Client-Cert-Info": 'Subject="OU=Unprivileged,DN=Testing";'
        'Issuer="OU=Suila,DN=Authority"'
    }
    headers_user_no_subject = {
        "X-Forwarded-Tls-Client-Cert-Info": 'Issuer="OU=Suila,DN=Authority"'
    }

    def requires_auth(self, path):
        self.assertEqual(
            self.client.get(path, headers={}).status_code,
            401,
            f"{path} did not return HTTP 401 for unauthenticated user",
        )
        self.assertEqual(
            self.client.get(path, headers=self.headers_user_not_found).status_code,
            401,
            f"{path} did not return HTTP 401 for nonexisting user",
        )
        self.assertEqual(
            self.client.get(path, headers=self.headers_user_no_subject).status_code,
            401,
            f"{path} did not return HTTP 401 for user with no cert subject",
        )
        self.assertEqual(
            self.client.get(path, headers=self.headers_user_unprivileged).status_code,
            403,
            f"{path} did not return HTTP 403 for unprivileged user",
        )

    def expect_get(self, url: str, item: Dict):
        self.requires_auth(url)
        response = self.client.get(url, headers=self.headers_user_accepted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), item)

    def expect_404(self, url: str):
        self.requires_auth(url)
        response = self.client.get(url, headers=self.headers_user_accepted)
        self.assertEqual(response.status_code, 404)

    def expect_list(self, url: str, *items: Dict):
        self.requires_auth(url)
        response = self.client.get(url, headers=self.headers_user_accepted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "count": len(items),
                "items": list(items),
            },
            f"response: {response.json()['items']} does not match {items}",
        )


class PersonApiTest(ApiTestCase):

    controller = PersonAPI

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person1 = Person.objects.create(
            name="Oluf Sand",
            cpr="1234567890",
            full_address="Det Mørke Jylland",
            location_code="123",
        )
        cls.expected1 = {
            "address_line_1": None,
            "address_line_2": None,
            "address_line_3": None,
            "address_line_4": None,
            "address_line_5": None,
            "civil_state": None,
            "cpr": "1234567890",
            "full_address": "Det Mørke Jylland",
            "location_code": "123",
            "name": "Oluf Sand",
        }
        cls.person2 = Person.objects.create(
            name="Anders Sand",
            cpr="2233445566",
            full_address="Det Lidt Lysere Jylland",
            location_code="456",
        )
        cls.expected2 = {
            "address_line_1": None,
            "address_line_2": None,
            "address_line_3": None,
            "address_line_4": None,
            "address_line_5": None,
            "civil_state": None,
            "cpr": "2233445566",
            "full_address": "Det Lidt Lysere Jylland",
            "location_code": "456",
            "name": "Anders Sand",
        }

    def test_get(self):
        self.expect_get("/api/person/1234567890", self.expected1)
        self.expect_404("/api/person/0000000000")

    def test_list_by_cpr(self):
        self.expect_list("/api/person?cpr=2233445566", self.expected2)
        self.expect_list("/api/person?cpr=0000000000")  # no items

    def test_list_by_name(self):
        self.expect_list("/api/person?name=Anders sand", self.expected2)
        self.expect_list("/api/person?name=Benny Nåså")  # no items

    def test_list_by_name_contains(self):
        self.expect_list("/api/person?name_contains=Oluf", self.expected1)
        self.expect_list(
            "/api/person?name_contains=Sand", self.expected1, self.expected2
        )
        self.expect_list("/api/person?name_contains=Benny")  # no items

    def test_list_by_address_contains(self):
        self.expect_list("/api/person?address_contains=Mørke", self.expected1)
        self.expect_list(
            "/api/person?address_contains=Jylland", self.expected1, self.expected2
        )
        self.expect_list("/api/person?address_contains=Fyn")  # no items

    def test_list_by_location_code(self):
        self.expect_list("/api/person?location_code=123", self.expected1)
        self.expect_list("/api/person?location_code=456", self.expected2)
        self.expect_list("/api/person?location_code=789")  # no items


class PersonYearApiTest(ApiTestCase):

    controller = PersonYearAPI

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year1 = Year.objects.create(year=2024)
        cls.year2 = Year.objects.create(year=2025)
        cls.person1 = Person.objects.create(
            name="Oluf Sand",
            cpr="1234567890",
            full_address="Det Mørke Jylland",
            location_code="123",
        )
        cls.personyear1a = PersonYear.objects.create(
            person=cls.person1,
            year=cls.year1,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="TwelveMonthsSummationEngine",
            tax_scope="FULD",
        )
        cls.personyear1b = PersonYear.objects.create(
            person=cls.person1,
            year=cls.year2,
            preferred_estimation_engine_a="MonthlyContinuationEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
            tax_scope="DELVIS",
        )
        cls.expected1a = {
            "year": 2024,
            "cpr": "1234567890",
            "preferred_estimation_engine_a": "InYearExtrapolationEngine",
            "preferred_estimation_engine_b": "TwelveMonthsSummationEngine",
            "tax_scope": "FULD",
            "in_quarantine": False,
            "quarantine_reason": "",
            "stability_score_a": None,
            "stability_score_b": None,
        }
        cls.expected1b = {
            "year": 2025,
            "cpr": "1234567890",
            "preferred_estimation_engine_a": "MonthlyContinuationEngine",
            "preferred_estimation_engine_b": "SelfReportedEngine",
            "tax_scope": "DELVIS",
            "in_quarantine": False,
            "quarantine_reason": "",
            "stability_score_a": None,
            "stability_score_b": None,
        }
        cls.person2 = Person.objects.create(
            name="Anders Sand",
            cpr="2233445566",
            full_address="Det Lidt Lysere Jylland",
            location_code="456",
        )
        cls.personyear2a = PersonYear.objects.create(
            person=cls.person2,
            year=cls.year1,
            preferred_estimation_engine_a="TwelveMonthsSummationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
            tax_scope="DELVIS",
        )
        cls.personyear2b = PersonYear.objects.create(
            person=cls.person2,
            year=cls.year2,
            preferred_estimation_engine_a="TwoYearSummationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
            tax_scope="FULD",
        )
        cls.expected2a = {
            "year": 2024,
            "cpr": "2233445566",
            "preferred_estimation_engine_a": "TwelveMonthsSummationEngine",
            "preferred_estimation_engine_b": "InYearExtrapolationEngine",
            "tax_scope": "DELVIS",
            "in_quarantine": False,
            "quarantine_reason": "",
            "stability_score_a": None,
            "stability_score_b": None,
        }
        cls.expected2b = {
            "year": 2025,
            "cpr": "2233445566",
            "preferred_estimation_engine_a": "TwoYearSummationEngine",
            "preferred_estimation_engine_b": "InYearExtrapolationEngine",
            "tax_scope": "FULD",
            "in_quarantine": False,
            "quarantine_reason": "",
            "stability_score_a": None,
            "stability_score_b": None,
        }

    def test_get(self):
        self.expect_get("/api/personyear/1234567890/2024", self.expected1a)
        self.expect_get("/api/personyear/2233445566/2025", self.expected2b)
        self.expect_404("/api/personyear/2233445566/2026")

    def test_list_by_cpr(self):
        self.expect_list(
            "/api/personyear?cpr=2233445566", self.expected2a, self.expected2b
        )
        self.expect_list("/api/personyear?cpr=0000000000")  # no items

    def test_list_by_year(self):
        self.expect_list("/api/personyear?year=2025", self.expected1b, self.expected2b)
        self.expect_list("/api/personyear?year=2026")  # no items

    def test_list_by_cpr_year(self):
        self.expect_list("/api/personyear?cpr=2233445566&year=2024", self.expected2a)
        self.expect_list("/api/personyear?cpr=2233445566&year=2025", self.expected2b)
        self.expect_list("/api/personyear?cpr=2233445566&year=2026")  # no items


class PersonMonthApiTest(ApiTestCase):

    controller = PersonMonthAPI

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year1 = Year.objects.create(year=2024)
        cls.year2 = Year.objects.create(year=2025)
        cls.person1 = Person.objects.create(
            name="Oluf Sand",
            cpr="1234567890",
            full_address="Det Mørke Jylland",
            location_code="123",
        )
        cls.personyear1 = PersonYear.objects.create(
            person=cls.person1,
            year=cls.year1,
        )
        cls.personyear2 = PersonYear.objects.create(
            person=cls.person1,
            year=cls.year2,
        )
        cls.personmonth1a = PersonMonth.objects.create(
            person_year=cls.personyear1,
            month=12,
            import_date=datetime.today(),
            municipality_code=573,
            municipality_name="Varde",
            fully_tax_liable=False,
            amount_sum=Decimal(10000),
            estimated_year_result=Decimal(120000),
            benefit_paid=Decimal(1000),
            estimated_year_benefit=Decimal(12000),
            actual_year_benefit=Decimal(12000),
        )
        cls.personmonth1b = PersonMonth.objects.create(
            person_year=cls.personyear2,
            month=1,
            import_date=datetime.today(),
            municipality_code=573,
            municipality_name="Varde",
            fully_tax_liable=False,
            amount_sum=Decimal(11000),
            estimated_year_result=Decimal(132000),
            benefit_paid=Decimal(1100),
            estimated_year_benefit=Decimal(13200),
            actual_year_benefit=Decimal(13200),
        )
        cls.personmonth1c = PersonMonth.objects.create(
            person_year=cls.personyear2,
            month=2,
            import_date=datetime.today(),
            municipality_code=573,
            municipality_name="Varde",
            fully_tax_liable=False,
            amount_sum=Decimal(12000),
            estimated_year_result=Decimal(144000),
            benefit_paid=Decimal(1200),
            estimated_year_benefit=Decimal(14400),
            actual_year_benefit=Decimal(14400),
        )
        MonthlyIncomeReport.objects.create(
            person_month=cls.personmonth1a,
            salary_income=Decimal(8000),
            catchsale_income=Decimal(2000),
            public_assistance_income=Decimal(0),
            alimony_income=Decimal(0),
            dis_gis_income=Decimal(0),
            retirement_pension_income=Decimal(0),
            disability_pension_income=Decimal(0),
            ignored_benefits_income=Decimal(0),
            employer_paid_gl_pension_income=Decimal(0),
            foreign_pension_income=Decimal(0),
            civil_servant_pension_income=Decimal(0),
            other_pension_income=Decimal(0),
            capital_income=Decimal(0),
        )
        MonthlyIncomeReport.objects.create(
            person_month=cls.personmonth1b,
            salary_income=Decimal(8000),
            catchsale_income=Decimal(3000),
            public_assistance_income=Decimal(0),
            alimony_income=Decimal(0),
            dis_gis_income=Decimal(0),
            retirement_pension_income=Decimal(0),
            disability_pension_income=Decimal(0),
            ignored_benefits_income=Decimal(0),
            employer_paid_gl_pension_income=Decimal(0),
            foreign_pension_income=Decimal(0),
            civil_servant_pension_income=Decimal(0),
            other_pension_income=Decimal(0),
            capital_income=Decimal(0),
        )
        MonthlyIncomeReport.objects.create(
            person_month=cls.personmonth1c,
            salary_income=Decimal(8000),
            catchsale_income=Decimal(4000),
            public_assistance_income=Decimal(0),
            alimony_income=Decimal(0),
            dis_gis_income=Decimal(0),
            retirement_pension_income=Decimal(0),
            disability_pension_income=Decimal(0),
            ignored_benefits_income=Decimal(0),
            employer_paid_gl_pension_income=Decimal(0),
            foreign_pension_income=Decimal(0),
            civil_servant_pension_income=Decimal(0),
            other_pension_income=Decimal(0),
            capital_income=Decimal(0),
        )

        cls.expected1a = {
            "year": 2024,
            "month": 12,
            "cpr": "1234567890",
            "income": "10000.00",
            "municipality_code": 573,
            "municipality_name": "Varde",
            "fully_tax_liable": False,
            "estimated_year_result": "120000.00",
            "estimated_year_benefit": "12000.00",
            "actual_year_benefit": "12000.00",
            "prior_benefit_paid": None,
            "benefit_paid": "1000.00",
            "a_income": "10000.00",
            # "b_income": "0.00",
            # "b_income_from_year": "0",
            "payout_date": "2024-12-17",
        }
        cls.expected1b = {
            "year": 2025,
            "month": 1,
            "cpr": "1234567890",
            "income": "11000.00",
            "municipality_code": 573,
            "municipality_name": "Varde",
            "fully_tax_liable": False,
            "estimated_year_result": "132000.00",
            "estimated_year_benefit": "13200.00",
            "actual_year_benefit": "13200.00",
            "prior_benefit_paid": None,
            "benefit_paid": "1100.00",
            "a_income": "11000.00",
            # "b_income": "0.00",
            # "b_income_from_year": "0",
            "payout_date": "2025-01-21",
        }
        cls.expected1c = {
            "year": 2025,
            "month": 2,
            "cpr": "1234567890",
            "income": "12000.00",
            "municipality_code": 573,
            "municipality_name": "Varde",
            "fully_tax_liable": False,
            "estimated_year_result": "144000.00",
            "estimated_year_benefit": "14400.00",
            "actual_year_benefit": "14400.00",
            "prior_benefit_paid": None,
            "benefit_paid": "1200.00",
            "a_income": "12000.00",
            # "b_income": "0.00",
            # "b_income_from_year": "0",
            "payout_date": "2025-02-18",
        }

        cls.person2 = Person.objects.create(
            name="Anders Sand",
            cpr="2233445566",
            full_address="Det Lidt Lysere Jylland",
            location_code="456",
        )
        cls.personyear2a = PersonYear.objects.create(
            person=cls.person2,
            year=cls.year1,
        )
        cls.personmonth2a = PersonMonth.objects.create(
            person_year=cls.personyear2a,
            month=12,
            import_date=datetime.today(),
            municipality_code=561,
            municipality_name="Esbjerg",
            fully_tax_liable=False,
            amount_sum=Decimal(0),
            estimated_year_result=Decimal(0),
            benefit_paid=Decimal(0),
            estimated_year_benefit=Decimal(0),
            actual_year_benefit=Decimal(0),
        )
        cls.expected2a = {
            "year": 2024,
            "month": 12,
            "cpr": "2233445566",
            "income": "0.00",
            "municipality_code": 561,
            "municipality_name": "Esbjerg",
            "fully_tax_liable": False,
            "estimated_year_result": "0.00",
            "estimated_year_benefit": "0.00",
            "actual_year_benefit": "0.00",
            "prior_benefit_paid": None,
            "benefit_paid": "0.00",
            "a_income": None,
            # "b_income": None,
            # "b_income_from_year": "0",
            "payout_date": "2024-12-17",
        }

    def test_get(self):
        self.expect_get("/api/personmonth/1234567890/2024/12", self.expected1a)
        self.expect_get("/api/personmonth/1234567890/2025/1", self.expected1b)
        self.expect_404("/api/personmonth/1234567890/2025/3")

    def test_list_by_cpr(self):
        self.expect_list(
            "/api/personmonth?cpr=1234567890",
            self.expected1a,
            self.expected1b,
            self.expected1c,
        )
        self.expect_list("/api/personmonth?cpr=0000000000")  # no items

    def test_list_by_year(self):
        self.expect_list("/api/personmonth?year=2024", self.expected1a, self.expected2a)
        self.expect_list("/api/personmonth?year=2025", self.expected1b, self.expected1c)
        self.expect_list("/api/personmonth?year=2026")  # no items

    def test_list_by_cpr_year(self):
        self.expect_list("/api/personmonth?cpr=1234567890&year=2024", self.expected1a)
        self.expect_list(
            "/api/personmonth?cpr=1234567890&year=2025",
            self.expected1b,
            self.expected1c,
        )
        self.expect_list("/api/personmonth?cpr=2233445566&year=2025")  # no items

    def test_list_by_cpr_year_month(self):
        self.expect_list(
            "/api/personmonth?cpr=1234567890&year=2025&month=1", self.expected1b
        )
        self.expect_list(
            "/api/personmonth?cpr=2233445566&year=2024&month=12", self.expected2a
        )
        self.expect_list(
            "/api/personmonth?cpr=2233445566&year=2025&month=1"
        )  # no items


class ApiDocTest(TestCase):

    def test_nonce(self):
        response = self.client.get("/api/docs")
        nonce = re.search(
            r"'nonce-([\w+=/]+)'",
            response.headers["Content-Security-Policy"],
        ).group(1)
        self.assertIsNotNone(nonce)
        dom = BeautifulSoup(response.content, "html.parser")
        for script_tag in dom.find_all("script"):
            self.assertTrue(script_tag.has_attr("nonce"))
            self.assertEqual(script_tag["nonce"], nonce)
        for script_tag in dom.find_all("link"):
            self.assertTrue(script_tag.has_attr("nonce"))
            self.assertEqual(script_tag["nonce"], nonce)
