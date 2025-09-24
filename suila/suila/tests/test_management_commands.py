# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import Future
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Set
from unittest.mock import ANY, MagicMock, call, patch

import numpy as np
import pandas as pd
from common.tests.test_utils import BaseTestCase
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connections
from django.forms import model_to_dict
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from requests.exceptions import HTTPError

from suila.models import JobLog, ManagementCommands, Person, PersonYear, StatusChoices


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


class CreateGroups(TestCase):
    def test_create_skattestyrelsen(self):
        call_command("create_groups")
        group = Group.objects.get(name="Skattestyrelsen")

        permissions = [p.codename for p in group.permissions.all()]

        self.assertIn("view_annualincome", permissions)
        self.assertIn("view_btaxpayment", permissions)
        self.assertIn("view_eboksmessage", permissions)
        self.assertIn("view_employer", permissions)
        self.assertIn("view_incomeestimate", permissions)
        self.assertIn("view_monthlyincomereport", permissions)
        self.assertIn("view_note", permissions)
        self.assertIn("view_noteattachment", permissions)
        self.assertIn("change_person", permissions)
        self.assertIn("view_data_analysis", permissions)
        self.assertIn("view_person", permissions)
        self.assertIn("view_personmonth", permissions)
        self.assertIn("view_personyear", permissions)
        self.assertIn("change_personyear", permissions)
        self.assertIn("view_personyearassessment", permissions)
        self.assertIn("view_personyearestimatesummary", permissions)
        self.assertIn("view_personyearu1aassessment", permissions)
        self.assertIn("can_download_reports", permissions)
        self.assertIn("use_adminsite_calculator_parameters", permissions)
        self.assertIn("view_year", permissions)

        self.assertEqual(len(permissions), 20)

    def test_create_borgerservice(self):
        call_command("create_groups")
        group = Group.objects.get(name="Borgerservice")

        permissions = [p.codename for p in group.permissions.all()]

        self.assertIn("view_annualincome", permissions)
        self.assertIn("view_btaxpayment", permissions)
        self.assertIn("view_eboksmessage", permissions)
        self.assertIn("view_employer", permissions)
        self.assertIn("view_incomeestimate", permissions)
        self.assertIn("view_monthlyincomereport", permissions)
        self.assertIn("view_note", permissions)
        self.assertIn("view_noteattachment", permissions)
        self.assertIn("view_person", permissions)
        self.assertIn("view_personmonth", permissions)
        self.assertIn("view_personyear", permissions)
        self.assertIn("view_personyearassessment", permissions)
        self.assertIn("view_personyearestimatesummary", permissions)
        self.assertIn("view_personyearu1aassessment", permissions)
        self.assertIn("view_year", permissions)

        self.assertEqual(len(permissions), 15)


class GetPersonInfoFromDAFO(TransactionTestCase):
    maxDiff = None

    def setUp(self):
        self.submit_patcher = patch(
            "suila.management.commands.get_person_info_from_dafo."
            "ThreadPoolExecutor.submit"
        )
        self.pitu_client_patcher = patch(
            "suila.management.commands.get_person_info_from_dafo.PituClient"
        )

        self.submit_mock = self.submit_patcher.start()
        self.pitu_client_mock = self.pitu_client_patcher.start()

        self.addCleanup(self.submit_mock.stop)
        self.addCleanup(self.pitu_client_mock.stop)

        # Mock ThreadPoolExecutor.submit to close connections when done
        # This allows for proper teardown of the test database
        def on_done(future):
            connections.close_all()

        def mock_submit(func, obj):
            future = Future()
            future.set_result(func(obj))
            future.add_done_callback(on_done)
            return future

        self.submit_mock.side_effect = mock_submit

        self.client_mock = self._get_mock_pitu_client()

        self.pitu_client_mock.from_settings.return_value = self.client_mock

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_no_persons(self, mock_get_pitu_client: MagicMock):
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
        )

        mock_get_pitu_client.assert_not_called()

    def test_http_404(self):
        # Test data
        self._create_person("0101709988")

        # Mocking
        response = MagicMock(status_code=404)
        self.client_mock.get_person_info.side_effect = HTTPError(response=response)
        self.pitu_client_mock.from_settings.return_value = self.client_mock

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        self.assertIn("Could not find person", stdout.getvalue())

    @patch("suila.management.commands.get_person_info_from_dafo.Command.update_person")
    def test_error_processing_person(self, update_person_mock: MagicMock):
        # Test data
        self._create_person("0101709988")

        # Mocking
        update_person_mock.side_effect = ValueError("foo")

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        self.assertIn("Error processing person: foo", stdout.getvalue())

    def test_unexpected_http_error(self):
        # Test data
        self._create_person("0101709988")

        # Mocking
        response = MagicMock(status_code=303)
        self.client_mock.get_person_info.side_effect = HTTPError(response=response)
        self.pitu_client_mock.from_settings.return_value = self.client_mock

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        self.assertIn("Unexpected 303 error", stdout.getvalue())

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_persons_with_no_personinfo(self, mock_get_pitu_client: MagicMock):
        # Test data
        person1 = self._create_person("0101709988")
        person2 = self._create_person("0102808877")
        person3 = self._create_person("0103907766")

        # Mocking
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

        self.assertEqual(
            mock_get_pitu_client.return_value.get_person_info.call_count, 3
        )
        mock_get_pitu_client.return_value.get_person_info.assert_has_calls(
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
                "allow_pause": True,
                "pause_reason": None,
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
                "annual_income_estimate": None,
                "cpr_status": 1,
            },
        )

        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person2.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person2.cpr,
                "paused": ANY,
                "allow_pause": True,
                "pause_reason": None,
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
                "annual_income_estimate": None,
                "cpr_status": 1,
            },
        )

        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person3.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person3.cpr,
                "paused": True,
                "allow_pause": True,
                "pause_reason": ANY,
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
                "annual_income_estimate": None,
                "cpr_status": 70,
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
        )
        self._create_person(
            "0102808877",
            name="Test Two Magenta",
            full_address="Silkeborgvej 261, 8230 Åbyhøj",
            country_code="DK",
        )
        person3 = self._create_person("0103907766")
        person4 = self._create_person("0104906655")

        # Mocking
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

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_person_from_cpr(self, mock_get_pitu_client: MagicMock):
        # Mocking
        mock_get_pitu_client.return_value = self._get_mock_pitu_client()

        # Verify nothing happens if the person already have DAFO data
        person1 = self._create_person(
            "0101709988",
            name="Test One Magenta",
            full_address="Silkeborgvej 260, 8230 Åbyhøj",
            country_code="DK",
        )
        call_command(ManagementCommands.GET_PERSON_INFO_FROM_DAFO, cpr=person1.cpr)
        mock_get_pitu_client.return_value.assert_not_called()

        # Verify DAFO-data is fetched for a person without any DAFO-data
        person2 = self._create_person("0102808877")
        call_command(ManagementCommands.GET_PERSON_INFO_FROM_DAFO, cpr=person2.cpr)
        mock_get_pitu_client.return_value.get_person_info.assert_called_with(
            person2.cpr
        )
        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person2.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person2.cpr,
                "paused": ANY,
                "allow_pause": True,
                "pause_reason": None,
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
                "annual_income_estimate": None,
                "cpr_status": 1,
            },
        )

        # Verify DAFO-data is fetched for a person missing more than one of
        # the key DAFO-data-fields ("full_address" & "country_code" in this case)
        person3 = self._create_person("0103907766", name="Test 3")
        call_command(ManagementCommands.GET_PERSON_INFO_FROM_DAFO, cpr=person3.cpr)
        mock_get_pitu_client.return_value.get_person_info.assert_called_with(
            person3.cpr
        )
        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person3.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person3.cpr,
                "paused": True,
                "allow_pause": True,
                "pause_reason": ANY,
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
                "annual_income_estimate": None,
                "cpr_status": 70,
            },
        )

        # Verify DAFO-data is fetched for personens missing "just one" of
        # the key DAFO-data-fields.
        person4 = self._create_person(
            "0104906655", name="Test 4", full_address="Testvej 1337, 8000 Aarhus C"
        )
        call_command(ManagementCommands.GET_PERSON_INFO_FROM_DAFO, cpr=person4.cpr)
        mock_get_pitu_client.return_value.get_person_info.assert_called_with(
            person4.cpr
        )
        self.assertEqual(
            model_to_dict(Person.objects.get(pk=person4.id)),
            {
                "id": ANY,
                "load": None,
                "cpr": person4.cpr,
                "paused": True,
                "allow_pause": True,
                "pause_reason": ANY,
                "name": "Test Four Magenta",
                "address_line_1": None,
                "address_line_2": None,
                "address_line_3": None,
                "address_line_4": None,
                "address_line_5": None,
                "full_address": "Silkeborgvej 263, 8230 Åbyhøj",
                "foreign_address": None,
                "country_code": "DK",
                "civil_state": None,
                "location_code": None,
                "welcome_letter": ANY,
                "welcome_letter_sent_at": ANY,
                "annual_income_estimate": None,
                "cpr_status": 90,
            },
        )

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_force_flag_no_cpr(self, mock_get_pitu_client: MagicMock):
        mock_get_pitu_client.return_value = self._get_mock_pitu_client()

        # Create test data
        person1 = self._create_person(
            "0101709988",
            name="Test 1",
            full_address="TestVej 1337, 1234 Oslo",
            country_code="NO",
        )
        person2 = self._create_person(
            "0102808877",
            name="Test 2",
            full_address="TestVej 2337, 1234 Oslo",
            country_code="NO",
        )

        # Invoke the CMD & assert
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            force=True,
        )

        self.assertEqual(
            mock_get_pitu_client.return_value.get_person_info.call_count, 2
        )
        mock_get_pitu_client.return_value.get_person_info.assert_has_calls(
            [
                call(person1.cpr),
                call(person2.cpr),
            ]
        )

        self.assertEqual(
            [model_to_dict(person) for person in Person.objects.all().order_by("pk")],
            [
                {
                    "id": ANY,
                    "load": None,
                    "cpr": person1.cpr,
                    "paused": ANY,
                    "allow_pause": True,
                    "pause_reason": None,
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
                    "annual_income_estimate": None,
                    "cpr_status": 1,
                },
                {
                    "id": ANY,
                    "load": None,
                    "cpr": person2.cpr,
                    "paused": ANY,
                    "allow_pause": True,
                    "pause_reason": None,
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
                    "annual_income_estimate": None,
                    "cpr_status": 1,
                },
            ],
        )

    @patch(
        "suila.management.commands.get_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_force_flag_for_cpr(self, mock_get_pitu_client: MagicMock):
        mock_get_pitu_client.return_value = self._get_mock_pitu_client()

        person1 = self._create_person(
            "0101709988",
            name="Test 1",
            full_address="TestVej 1337, 1234 Oslo",
            country_code="NO",
        )

        # Invoke & assert
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            cpr=person1.cpr,
            force=True,
        )
        mock_get_pitu_client.return_value.get_person_info.assert_called_once_with(
            "0101709988"
        )

    def test_no_civilstand(self):
        # Test data
        self._create_person("0101709988")

        # Mocking
        person_info = self._mock_get_person_info("0101709988")
        person_info.pop("civilstand")
        self.client_mock.get_person_info.return_value = person_info
        self.client_mock.get_person_info.side_effect = None
        self.pitu_client_mock.from_settings.return_value = self.client_mock

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )

        self.assertIn('no "civilstand" in person_data', stdout.getvalue())

    def test_no_first_name(self):
        # Test data
        self._create_person("0101709988")

        # Mocking
        person_info = self._mock_get_person_info("0101709988")
        person_info.pop("fornavn")
        self.client_mock.get_person_info.return_value = person_info
        self.client_mock.get_person_info.side_effect = None
        self.pitu_client_mock.from_settings.return_value = self.client_mock

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        self.assertIn('no "fornavn" and "efternavn" in person_data', stdout.getvalue())

    def test_no_last_name(self):
        # Test data
        self._create_person("0101709988")

        # Mocking
        person_info = self._mock_get_person_info("0101709988")
        person_info.pop("efternavn")
        self.client_mock.get_person_info.return_value = person_info
        self.client_mock.get_person_info.side_effect = None
        self.pitu_client_mock.from_settings.return_value = self.client_mock

        stdout = StringIO()
        call_command(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            verbosity=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        self.assertIn('no "fornavn" and "efternavn" in person_data', stdout.getvalue())

    @patch(
        "suila.management.commands."
        "get_updated_person_info_from_dafo.Command._get_pitu_client"
    )
    def test_get_updated_since(self, mock_get_pitu_client: MagicMock):
        mock_get_pitu_client.return_value = self._get_mock_pitu_client()
        person1 = self._create_person(
            "0101709988",
            name="Test One Magenta",
            full_address="Silkeborgvej 260, 8230 Åbyhøj",
            country_code="DK",
        )
        person2 = self._create_person(
            "0102808877",
            name="Test Two Magenta",
            full_address="Silkeborgvej 260, 8230 Åbyhøj",
            country_code="DK",
        )
        JobLog.objects.filter(
            name=ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO
        ).delete()
        last_run = JobLog.objects.create(
            name=ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
            status=StatusChoices.SUCCEEDED,
        )
        last_run.runtime = timezone.now() - timedelta(
            days=1
        )  # runtime has auto_now_add=True, so we can't set it in create()
        last_run.save()
        call_command(
            ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
        )
        mock_get_pitu_client.return_value.get_person_info.assert_called_with(
            person1.cpr
        )
        self.assertNotIn(
            call(person2.cpr),
            mock_get_pitu_client.return_value.get_person_info.mock_calls,
        )

    # PRIVATE helper methods
    def _get_mock_pitu_client(self) -> MagicMock:
        mock_get_person_info = MagicMock(
            side_effect=GetPersonInfoFromDAFO._mock_get_person_info
        )
        mock_get_subscription_results = MagicMock(
            side_effect=GetPersonInfoFromDAFO._mock_get_subscription_results
        )
        mock_pitu_client = MagicMock(
            get_person_info=mock_get_person_info,
            get_subscription_results=mock_get_subscription_results,
        )
        return mock_pitu_client

    def _create_person(self, cpr: str, **kwargs):
        return Person.objects.create(cpr=cpr, **kwargs)

    @staticmethod
    def _mock_get_subscription_results(last_update_time: datetime | None) -> Set[str]:
        updated = set()
        if last_update_time < timezone.now() - timedelta(hours=12):
            updated.add("0101709988")
        if last_update_time < timezone.now() - timedelta(days=1, hours=12):
            updated.add("0102808877")
        return updated

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
                    "statuskode": 1,  # 1="bopæl i Danmark"
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
                    "statuskode": 1,  # 1="bopæl i Danmark"
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
                    "statuskode": 70,  # 70="forsvundet"
                }
            case "0104906655":
                return {
                    "civilstand": None,
                    "fornavn": "Test Four",
                    "efternavn": "Magenta",
                    "adresse": "Silkeborgvej 263",
                    "bynavn": "Åbyhøj",
                    "postnummer": "8230",
                    "udlandsadresse": None,
                    "landekode": "DK",
                    "statuskode": 90,  # 90="død"
                }


class CreateApiGroup(TestCase):
    def test_create_api_group(self):
        call_command("create_api_group", "api")
        api_group = Group.objects.get(name="api")

        permissions = [p.codename for p in api_group.permissions.all()]
        self.assertIn("view_person", permissions)
        self.assertIn("view_year", permissions)
        self.assertIn("view_personyear", permissions)
        self.assertIn("view_personmonth", permissions)
        self.assertEqual(len(permissions), 4)
