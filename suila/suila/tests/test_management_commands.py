# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import StringIO
from typing import Any, Dict
from unittest.mock import ANY, MagicMock, call, patch

import numpy as np
import pandas as pd
from common.tests.test_utils import BaseTestCase
from django.core.management import call_command
from django.forms import model_to_dict
from django.test import TestCase

from suila.models import ManagementCommands, Person, PersonYear


class CalculateStabilityScoreTest(BaseTestCase):

    def test_calculate_stability_score(self):

        for person_year in PersonYear.objects.all():
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)

        self.call_command("calculate_stability_score", self.year, verbosity=3)
        for person_year in PersonYear.objects.filter(year__year=self.year.year + 1):
            self.assertGreater(person_year.stability_score_a, 0)
            self.assertGreater(person_year.stability_score_b, 0)

    @patch(
        "suila.management.commands.calculate_stability_score."
        "calculate_stability_score_for_entire_year"
    )
    def test_calculate_stability_score_nan_stability_scores(
        self, calculate_stability_score_for_entire_year
    ):
        df = pd.DataFrame(index=["1234567890", "1234567891"])

        df["A"] = [np.nan, np.nan]
        df["B"] = [np.nan, np.nan]

        calculate_stability_score_for_entire_year.return_value = df
        self.call_command("calculate_stability_score", self.year)

        for person_year in PersonYear.objects.all():
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)

    @patch(
        "suila.management.commands.calculate_stability_score."
        "calculate_stability_score_for_entire_year"
    )
    def test_calculate_stability_score_missing_person(
        self, calculate_stability_score_for_entire_year
    ):
        df = pd.DataFrame(index=["1234567890"])

        df["A"] = [1]
        df["B"] = [1]

        calculate_stability_score_for_entire_year.return_value = df
        self.call_command("calculate_stability_score", self.year)

        for person_year in PersonYear.objects.filter(
            person__cpr="1234567890", year__year=self.year.year + 1
        ):
            self.assertEqual(person_year.stability_score_a, 1)
            self.assertEqual(person_year.stability_score_b, 1)

        for person_year in PersonYear.objects.filter(
            person__cpr="1234567891", year__year=self.year.year + 1
        ):
            self.assertEqual(person_year.stability_score_a, None)
            self.assertEqual(person_year.stability_score_b, None)


class GetPersonInfoFromDAFO(TestCase):
    maxDiff = None

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_no_persons(self, mock_get_pitu_client: MagicMock):
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=StringIO(),
            stderr=StringIO(),
        )

        mock_get_pitu_client.assert_not_called()

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_persons_with_no_personinfo(self, mock_get_pitu_client: MagicMock):
        # Test data
        person1 = self._create_person("0101709988")
        person2 = self._create_person("0102808877")
        person3 = self._create_person("0103907766")

        # Mocking
        mock_get_person_info = MagicMock(
            side_effect=GetPersonInfoFromDAFO._mock_get_person_info
        )
        mock_pitu_client = MagicMock(get_person_info=mock_get_person_info)
        mock_get_pitu_client.return_value = mock_pitu_client

        # Invoke the command
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(mock_get_person_info.call_count, 3)
        mock_get_person_info.assert_has_calls(
            [
                call("0101709988"),
                call("0102808877"),
                call("0103907766"),
            ]
        )

        # Verify the persons got updated
        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person1.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person1.cpr,
                "paused": ANY,
                "name": "Test One Magenta",
                "address_line_1": None,
                "address_line_2": None,
                "address_line_3": None,
                "address_line_4": None,
                "address_line_5": None,
                "full_address": "Silkeborgvej 260, 8230 Åbyhøj",
                "foreign_address": None,
                "country_code": "DK",
                "civil_state": None,
                "location_code": None,
                "welcome_letter": ANY,
                "welcome_letter_sent_at": ANY,
            },
        )

        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person2.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person2.cpr,
                "paused": ANY,
                "name": "Test Two Magenta",
                "address_line_1": None,
                "address_line_2": None,
                "address_line_3": None,
                "address_line_4": None,
                "address_line_5": None,
                "full_address": "Silkeborgvej 261, 8230 Åbyhøj",
                "foreign_address": None,
                "country_code": "DK",
                "civil_state": None,
                "location_code": None,
                "welcome_letter": ANY,
                "welcome_letter_sent_at": ANY,
            },
        )

        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person3.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person3.cpr,
                "paused": ANY,
                "name": "Test Three Magenta",
                "address_line_1": None,
                "address_line_2": None,
                "address_line_3": None,
                "address_line_4": None,
                "address_line_5": None,
                "full_address": "Silkeborgvej 262, 8230 Åbyhøj",
                "foreign_address": None,
                "country_code": "DK",
                "civil_state": None,
                "location_code": None,
                "welcome_letter": ANY,
                "welcome_letter_sent_at": ANY,
            },
        )

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_persons_with_existing_personinfo(self, mock_get_pitu_client: MagicMock):
        # Test data
        self._create_person(
            "0101709988",
            name="Test One Magenta",
            full_address="Silkeborgvej 260, 8230 Åbyhøj",
            country_code="DK",
            civil_state=None,
            foreign_address=None,
        )
        self._create_person(
            "0102808877",
            name="Test Two Magenta",
            full_address="Silkeborgvej 261, 8230 Åbyhøj",
            country_code="DK",
            civil_state=None,
            foreign_address=None,
        )
        person3 = self._create_person("0103907766")
        person4 = self._create_person("0104906655")

        mock_get_pitu_client.return_value = self._get_mock_pitu_client()

        # Invoke the command
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=stderr,
        )

        # Should only fetch person-info for persons missing it, which in this test is 2
        self.assertEqual(
            mock_get_pitu_client.return_value.get_person_info.call_count, 2
        )
        mock_get_pitu_client.return_value.get_person_info.assert_has_calls(
            [
                call(person3.cpr),
                call(person4.cpr),
            ]
        )

    # PRIVATE helper methods
    def _get_mock_pitu_client(self) -> MagicMock:
        mock_get_person_info = MagicMock(
            side_effect=GetPersonInfoFromDAFO._mock_get_person_info
        )
        mock_pitu_client = MagicMock(get_person_info=mock_get_person_info)

        return mock_pitu_client

    def _create_person(self, cpr: str, **kwargs):
        return Person.objects.create(cpr=cpr, **kwargs)

    @staticmethod
    def _mock_get_person_info(cpr: str) -> Dict[str, Any]:
        match (cpr):
            case "0101709988":
                return {
                    "civilstand": None,
                    "fornavn": "Test One",
                    "efternavn": "Magenta",
                    "adresse": "Silkeborgvej 260",
                    "bynavn": "Åbyhøj",
                    "postnummer": "8230",
                    "udlandsadresse": None,
                    "landekode": "DK",
                }
            case "0102808877":
                return {
                    "civilstand": None,
                    "fornavn": "Test Two",
                    "efternavn": "Magenta",
                    "adresse": "Silkeborgvej 261",
                    "bynavn": "Åbyhøj",
                    "postnummer": "8230",
                    "udlandsadresse": None,
                    "landekode": "DK",
                }
            case "0103907766":
                return {
                    "civilstand": None,
                    "fornavn": "Test Three",
                    "efternavn": "Magenta",
                    "adresse": "Silkeborgvej 262",
                    "bynavn": "Åbyhøj",
                    "postnummer": "8230",
                    "udlandsadresse": None,
                    "landekode": "DK",
                }
