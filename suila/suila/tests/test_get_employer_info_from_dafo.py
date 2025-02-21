# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import Mock, patch

from django.test import TestCase

from suila.management.commands.get_employer_info_from_dafo import (
    Command as GetEmployerInfoFromDafoCommand,
)
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

    def _run(self, **kwargs):
        # Arrange
        kwargs.setdefault("verbosity", 0)
        kwargs.setdefault("cvr", None)
        command = GetEmployerInfoFromDafoCommand()
        mock_client = Mock()
        mock_client.get.return_value = self._mock_result
        with patch.object(command, "_get_pitu_client", return_value=mock_client):
            # Act
            command._handle(**kwargs)
