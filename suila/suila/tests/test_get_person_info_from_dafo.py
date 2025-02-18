# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import Mock, patch

from django.test import TestCase

from suila.management.commands.get_person_info_from_dafo import (
    Command as GetPersonInfoFromDafoCommand,
)
from suila.models import Person


class TestGetPersonInfoFromDafoCommand(TestCase):
    cpr = "3112700000"

    _mock_result = {
        "adresse": "Testvej 123",
        "adresseringsnavn": "Efternavn,Fornavn",
        "beskyttelsestyper": [],
        "bynavn": "Testby",
        "civilstand": "U",
        "cprNummer": cpr,
        "efternavn": "Efternavn",
        "far": cpr,
        "fornavn": "Fornavn",
        "kommune": "Testkommune",
        "køn": "M",
        "landekode": "GL",
        "lokalitetsforkortelse": "TES",
        "lokalitetsnavn": "Testlokalitet",
        "mor": cpr,
        "myndighedskode": 959,
        "postnummer": 9999,
        "statsborgerskab": 0,
        "statuskode": 5,
        "statuskodedato": "2000-01-01",
        "stedkode": 1000,
        "tilflytningsdato": "2020-01-01",
        "vejkode": 100,
    }

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person = Person.objects.create(cpr=cls.cpr)
        cls.other_person = Person.objects.create(cpr="0101012222")

    def test_all_persons_processed_if_no_cpr(self):
        # Act: run without `cpr` parameter
        self._run()
        # All `Person` objects are updated using the same mock CPR data
        self.assertQuerySetEqual(
            Person.objects.order_by("cpr").values_list("civil_state", flat=True),
            ["U"] * 2,
        )

    def test_person_is_updated(self):
        # Act: run with `cpr` parameter
        self._run(cpr=self.cpr)
        # Assert that all relevant fields on `Person` are updated as expected
        self.assertQuerySetEqual(
            Person.objects.filter(cpr=self.cpr).values(
                "cpr", "civil_state", "location_code", "name", "full_address"
            ),
            [
                {
                    "cpr": self.cpr,
                    "civil_state": "U",
                    "location_code": "959",
                    "name": "Fornavn Efternavn",
                    "full_address": "Testvej 123, 9999 Testby",
                },
            ],
        )

    def _run(self, **kwargs):
        # Arrange
        kwargs.setdefault("verbosity", 0)
        kwargs.setdefault("cpr", None)
        command = GetPersonInfoFromDafoCommand()
        mock_client = Mock()
        mock_client.get_person_info.return_value = self._mock_result
        with patch(
            "suila.management.commands.get_person_info_from_dafo."
            "PituClient.from_settings",
            return_value=mock_client,
        ):
            # Act
            command._handle(**kwargs)
