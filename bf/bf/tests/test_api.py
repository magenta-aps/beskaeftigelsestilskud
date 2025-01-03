from typing import Dict

from common.models import User
from django.test import TestCase
from ninja_extra.testing import TestClient

from bf.api import PersonAPI
from bf.api.personyear import PersonYearAPI
from bf.models import Person, PersonYear, Year


class ApiTestCase(TestCase):

    controller = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        response = self.client.get(
            url,
            headers=self.headers_user_accepted,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), item)

    def expect_list(self, url: str, *items: Dict):
        response = self.client.get(
            url,
            headers=self.headers_user_accepted,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "count": len(items),
                "items": list(items),
            },
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
        url = "/api/person/1234567890"
        self.requires_auth(url)

        self.expect_get(
            url,
            self.expected1,
        )

    def test_list_by_cpr(self):
        url = "/api/person?cpr=2233445566"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected2,
        )

    def test_list_by_name(self):
        url = "/api/person?name=Anders sand"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected2,
        )

    def test_list_by_name_contains(self):
        url = "/api/person?name_contains=Oluf"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected1,
        )

        url = "/api/person?name_contains=Sand"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected1,
            self.expected2,
        )

    def test_list_by_address_contains(self):
        url = "/api/person?address_contains=Mørke"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected1,
        )

        url = "/api/person?address_contains=Jylland"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected1,
            self.expected2,
        )

    def test_list_by_location_code(self):
        url = "/api/person?location_code=123"
        self.requires_auth(url)

        self.expect_list(url, self.expected1)

        url = "/api/person?location_code=456"
        self.requires_auth(url)

        self.expect_list(url, self.expected2)


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
            preferred_estimation_engine_a="SameAsLastMonthEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
            tax_scope="DELVIS",
        )
        cls.expected1a = {
            "year": 2024,
            "cpr": "1234567890",
            "preferred_estimation_engine_a": "InYearExtrapolationEngine",
            "preferred_estimation_engine_b": "TwelveMonthsSummationEngine",
            "tax_scope": "FULD",
        }
        cls.expected1b = {
            "year": 2025,
            "cpr": "1234567890",
            "preferred_estimation_engine_a": "SameAsLastMonthEngine",
            "preferred_estimation_engine_b": "SelfReportedEngine",
            "tax_scope": "DELVIS",
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
        }
        cls.expected2b = {
            "year": 2025,
            "cpr": "2233445566",
            "preferred_estimation_engine_a": "TwoYearSummationEngine",
            "preferred_estimation_engine_b": "InYearExtrapolationEngine",
            "tax_scope": "FULD",
        }

    def test_get(self):
        url = "/api/personyear/1234567890/2024"
        self.requires_auth(url)

        self.expect_get(
            url,
            self.expected1a,
        )
        url = "/api/personyear/2233445566/2025"
        self.requires_auth(url)

        self.expect_get(
            url,
            self.expected2b,
        )

    def test_list_by_cpr(self):
        url = "/api/personyear?cpr=2233445566"
        self.requires_auth(url)
        self.expect_list(url, self.expected2a, self.expected2b)

    def test_list_by_year(self):
        url = "/api/personyear?year=2025"
        self.requires_auth(url)
        self.expect_list(url, self.expected1b, self.expected2b)

    def test_list_by_cpr_year(self):
        url = "/api/personyear?cpr=2233445566&year=2024"
        self.requires_auth(url)

        self.expect_list(
            url,
            self.expected2a,
        )
