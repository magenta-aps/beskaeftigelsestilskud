from common.models import User
from django.test import TestCase

from bf.api import PersonAPI
from bf.models import Person


class ApiTestCase(TestCase):

    controller = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # cls.client = TestClient(cls.controller)
        cls.user = User.objects.create(
            username="test", is_superuser=True, cert_subject="OU=Suila,DN=Testing"
        )
        cls.user.set_password("test")
        cls.user.save()

        cls.unprivileged_user = User.objects.create(
            username="unprivileged", cert_subject="OU=Unprivileged,DN=Testing"
        )

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

    def requires_auth(self, path):
        self.assertEqual(
            self.client.get(
                path,
                # no headers
            ).status_code,
            401,
            f"{path} did not return HTTP 401 for unauthenticated user",
        )
        self.assertEqual(
            self.client.get(path, self.headers_user_not_found).status_code,
            401,
            f"{path} did not return HTTP 401 for nonexisting user",
        )
        self.assertEqual(
            self.client.get(path, self.headers_user_unprivileged).status_code,
            403,
            f"{path} did not return HTTP 403 for unprivileged user",
        )


class PersonApiTest(ApiTestCase):

    controller = PersonAPI

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person1 = Person.objects.create(
            name="Oluf Sand",
            cpr="1234567890",
        )
        cls.person2 = Person.objects.create(
            name="Anders Sand",
            cpr="1122334455",
        )

    def test_get(self):
        self.requires_auth("/api/person/1234567890")

        response = self.client.get(
            "/api/person/1234567890", headers=self.headers_user_accepted
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "address_line_1": None,
                "address_line_2": None,
                "address_line_3": None,
                "address_line_4": None,
                "address_line_5": None,
                "civil_state": None,
                "cpr": "1234567890",
                "full_address": None,
                "location_code": None,
                "name": "Oluf Sand",
            },
        )

    def test_list_by_cpr(self):
        self.requires_auth("/api/person?cpr=1122334455")

        response = self.client.get(
            "/api/person?cpr=1122334455",
            headers=self.headers_user_accepted,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "count": 1,
                "items": [
                    {
                        "address_line_1": None,
                        "address_line_2": None,
                        "address_line_3": None,
                        "address_line_4": None,
                        "address_line_5": None,
                        "civil_state": None,
                        "cpr": "1122334455",
                        "full_address": None,
                        "location_code": None,
                        "name": "Anders Sand",
                    },
                ],
            },
        )
