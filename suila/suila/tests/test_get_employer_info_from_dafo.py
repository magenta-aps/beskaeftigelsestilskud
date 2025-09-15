# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase
from requests.exceptions import HTTPError

from suila.models import Employer


class TestGetPersonInfoFromDafoCommand(TestCase):
    cvr = 12345678

    _mock_result = {
        "source": "CVR",
        "cvrNummer": cvr,
        "navn": "Firmanavn ApS",
        "forretningsområde": "Forretningsområdenavn",
        "statuskode": "NORMAL",
        "statuskodedato": "2000-01-01",
        "myndighedskode": 960,
        "kommune": "Kommunenavn",
        "vejkode": 100,
        "stedkode": 1000,
        "adresse": "Testvej 123, 1. sal",
        "postboks": 101,
        "postnummer": 9999,
        "bynavn": "Testby",
        "landekode": "GL",
        "email": "company@example.org",
        "telefon": "123456",
    }

    _mock_pitu_settings = {
        "certificate": "test_cert",
        "private_key": "test_key",
        "root_ca": "test_ca",
        "client_header": "test_header",
        "base_url": "test_url",
        "person_info_service": "test_cpr_service",
        "company_info_service": "test_cvr_service",
    }

    def setUp(self):
        self.pitu_client_patcher = patch(
            "suila.management.commands.get_employer_info_from_dafo.PituClient.get"
        )
        self.method_mock = self.pitu_client_patcher.start()
        self.method_mock.return_value = self._mock_result

    def tearDown(self):
        self.pitu_client_patcher.stop()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.employer = Employer.objects.create(cvr=cls.cvr)
        cls.other_employer = Employer.objects.create(cvr=87654321)

    def test_all_employers_processed_if_no_cvr(self):
        # Act: run without `cvr` parameter
        self._run()
        # All `Employer` objects are updated using the same mock CVR data
        self.assertQuerySetEqual(
            Employer.objects.order_by("cvr").values_list("name", flat=True),
            ["Firmanavn ApS"] * 2,
        )

    def test_employer_is_updated(self):
        # Act: run with `cvr` parameter
        self._run(cvr=self.cvr)
        # Assert that `Employer.name` is updated as expected
        self.assertQuerySetEqual(
            Employer.objects.filter(cvr=self.cvr).values("cvr", "name"),
            [{"cvr": self.cvr, "name": "Firmanavn ApS"}],
        )

    def test_no_employers(self):
        stdout = StringIO()
        self._run(cvr="1234", stdout=stdout, verbosity=3)
        self.assertIn("Could not find any employers", stdout.getvalue())

    def test_http_404(self):
        stdout = StringIO()
        response = MagicMock(status_code=404)
        self.method_mock.side_effect = HTTPError(response=response)
        self._run(stdout=stdout, verbosity=3)
        self.assertIn("Could not find employer", stdout.getvalue())

    def test_unexpected_http_error(self):
        stdout = StringIO()
        response = MagicMock(status_code=303)
        self.method_mock.side_effect = HTTPError(response=response)
        self._run(stdout=stdout, verbosity=3)
        self.assertIn("Unexpected 303 error", stdout.getvalue())

    def test_no_name(self):
        stdout = StringIO()
        mock_result = self._mock_result
        mock_result.pop("navn")
        self.method_mock.return_value = self._mock_result
        self._run(stdout=stdout, verbosity=3)
        self.assertIn("No employer name", stdout.getvalue())

    def _run(self, **kwargs):
        call_command("get_employer_info_from_dafo", **kwargs)
