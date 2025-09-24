# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
import os
import os.path
import re
import time
from concurrent.futures import Future
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import pandas as pd
import requests
from django.conf import settings
from django.core.files.temp import NamedTemporaryFile
from django.core.management import call_command as core_call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from requests import Response
from requests.exceptions import ConnectionError

from suila.integrations.eboks.client import (
    EboksClient,
    MessageCollisionException,
    MessageFailureException,
)
from suila.models import (
    EboksMessage,
    ManagementCommands,
    Person,
    PersonMonth,
    PersonYear,
    SuilaEboksMessage,
    TaxInformationPeriod,
    Year,
)


class EboksTest(TestCase):

    client_cert_file = NamedTemporaryFile(suffix=".crt")
    client_key_file = NamedTemporaryFile(suffix=".key")

    @property
    def data(self) -> bytes:
        with open(os.path.join(os.path.dirname(__file__), "test.pdf"), "rb") as f:
            return f.read()

    @classmethod
    def mock_response(cls, status_code: int = 200, content: bytes = b""):
        response = Response()
        response.status_code = status_code
        response._content = content
        return response

    @classmethod
    def test_settings(cls, **kwargs):
        return {
            **settings.EBOKS,
            "client_cert": cls.client_cert_file.name,
            "client_key": cls.client_key_file.name,
            **kwargs,
        }

    @staticmethod
    def mock_request(recipient_status, post_processing_status, fails=0, status=200):
        mock = MagicMock()

        def side_effect(method, url, params, data, **kwargs):
            if mock.fails > 0:
                mock.fails -= 1
                raise ConnectionError
            m = re.search(
                r"/int/rest/srv.svc/3/dispatchsystem/3994/dispatches/([^/]+)", url
            )
            if m is None:
                raise Exception("No match")
            message_id = m.group(1)

            response = Response()
            response.status_code = status
            if status == 200:
                response._content = json.dumps(
                    {
                        "message_id": message_id,
                        "recipients": [
                            {
                                "status": recipient_status,
                                "post_processing_status": post_processing_status,
                            }
                        ],
                    }
                ).encode("utf-8")
            return response

        mock.fails = fails
        mock.side_effect = side_effect
        return mock


@override_settings(EBOKS=EboksTest.test_settings())
class SendTest(EboksTest):

    @patch.object(requests.sessions.Session, "request")
    def test_pre_saved(self, mock_request):
        mock_request.side_effect = self.mock_request("", "")
        message = EboksMessage.objects.create(
            cpr_cvr="12345678",
            title="EboksTest",
            content_type=179343,
        )
        message.set_pdf_data(pdf_data=self.data)
        with EboksClient.from_settings() as client:
            message.send(client)
        mock_request.assert_called_with(
            "PUT",
            f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
            f"dispatchsystem/3994/dispatches/{message.message_id}",
            None,
            message.xml,
            timeout=60,
        )
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.recipient_status, "")
        self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_send_success(self, mock_request):
        mock_request.side_effect = self.mock_request("", "")
        message = EboksMessage.dispatch("12345678", "EboksTest", 179343, self.data)
        mock_request.assert_called_with(
            "PUT",
            f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
            f"dispatchsystem/3994/dispatches/{message.message_id}",
            None,
            message.xml,
            timeout=60,
        )
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.recipient_status, "")
        self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_send_postprocessing(self, mock_request):
        mock_request.side_effect = self.mock_request("exempt", "pending")
        message = EboksMessage.dispatch("12345678", "EboksTest", 179343, self.data)
        mock_request.assert_called_with(
            "PUT",
            f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
            f"dispatchsystem/3994/dispatches/{message.message_id}",
            None,
            message.xml,
            timeout=60,
        )
        self.assertEqual(message.status, "post_processing")
        self.assertEqual(message.recipient_status, "exempt")
        self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    @patch.object(time, "sleep")
    def test_send_collision(self, mock_sleep, mock_request):
        mock_sleep.return_value = None
        mock_request.side_effect = self.mock_request("exempt", "pending", 0, 419)
        message = EboksMessage(
            cpr_cvr="12345678", title="EboksTest", content_type=179343
        )
        message.set_pdf_data(self.data)
        with self.assertRaises(MessageCollisionException):
            message.send()
        mock_sleep.assert_not_called()
        self.assertEqual(message.status, "failed")

    @patch.object(requests.sessions.Session, "request")
    @patch.object(time, "sleep")
    def test_send_error(self, mock_sleep, mock_request):
        mock_sleep.return_value = None
        mock_request.side_effect = self.mock_request("exempt", "pending", 0, 400)
        message = EboksMessage(
            cpr_cvr="12345678", title="EboksTest", content_type=179343
        )
        message.set_pdf_data(self.data)
        with self.assertRaises(MessageFailureException):
            message.send()
        mock_sleep.assert_not_called()
        self.assertEqual(message.status, "failed")

    @patch.object(requests.sessions.Session, "request")
    def test_send_retry(self, mock_request):
        for blockings in range(1, 5):
            # Must patch inside loop to get correct number of sleep() calls
            with patch.object(time, "sleep") as mock_sleep:
                mock_sleep.return_value = None
                mock_request.side_effect = self.mock_request(
                    "exempt", "pending", blockings
                )
                message = EboksMessage.dispatch(
                    "12345678", "EboksTest", 179343, self.data
                )
                mock_request.assert_called_with(
                    "PUT",
                    f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
                    f"dispatchsystem/3994/dispatches/{message.message_id}",
                    None,
                    message.xml,
                    timeout=60,
                )
                mock_sleep.assert_called_with(10)
                self.assertEqual(len(mock_sleep.mock_calls), blockings)
                self.assertEqual(message.status, "post_processing")
                self.assertEqual(message.recipient_status, "exempt")
                self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_send_retry_errorcode(self, mock_request):
        with patch.object(time, "sleep") as mock_sleep:
            mock_sleep.return_value = None
            mock_request.side_effect = self.mock_request("exempt", "pending", 0, 500)
            message = EboksMessage(
                cpr_cvr="12345678", title="EboksTest", content_type=179343
            )
            message.set_pdf_data(self.data)
            with self.assertRaises(MessageFailureException):
                message.send()
            mock_request.assert_called_with(
                "PUT",
                f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
                f"dispatchsystem/3994/dispatches/{message.message_id}",
                None,
                message.xml,
                timeout=60,
            )
            mock_sleep.assert_called_with(10)
            self.assertEqual(len(mock_sleep.mock_calls), 5)
            self.assertEqual(message.status, "failed")
            self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_send_retry_fail(self, mock_request):
        with patch.object(time, "sleep") as mock_sleep:
            mock_sleep.return_value = None
            mock_request.side_effect = self.mock_request("exempt", "pending", 6)
            with self.assertRaises(
                Exception,
                msg="Failed to send message to ebox; "
                "retried 5 times spaced 10 seconds apart. Last exception was:",
            ):
                message = EboksMessage.dispatch(
                    "12345678", "EboksTest", 179343, self.data
                )
                mock_request.assert_called_with(
                    "PUT",
                    f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
                    f"dispatchsystem/3994/dispatches/{message.message_id}",
                    None,
                    message.xml,
                    timeout=60,
                )
                mock_sleep.assert_called_with(10)
                self.assertEqual(len(mock_sleep.mock_calls), 5)
                self.assertEqual(message.status, "post_processing")
                self.assertEqual(message.recipient_status, "exempt")
                self.assertIsNotNone(message.pk)


class EboksXmlTest(EboksTest):
    def test_generate_xml_company(self):
        xml = EboksMessage.generate_xml(
            "12345678", "EboksTest", 179343, self.data
        ).decode("utf-8")
        self.assertIsNotNone(re.search(r"<Id>12345678</Id>", xml))
        self.assertIsNotNone(re.search(r"<Type>V</Type>", xml))
        self.assertIsNotNone(re.search(r"<Nationality>DK</Nationality>", xml))
        self.assertIsNotNone(re.search(r"<ContentTypeId>179343</ContentTypeId>", xml))
        self.assertIsNotNone(re.search(r"<Title>EboksTest</Title>", xml))
        self.assertIsNotNone(re.search(r"<FileExtension>pdf</FileExtension>", xml))

    def test_generate_xml_person(self):
        xml = EboksMessage.generate_xml(
            "1234567890", "EboksTest", 179343, self.data
        ).decode("utf-8")
        self.assertIsNotNone(re.search(r"<Id>1234567890</Id>", xml))
        self.assertIsNotNone(re.search(r"<Type>P</Type>", xml))
        self.assertIsNotNone(re.search(r"<Nationality>DK</Nationality>", xml))
        self.assertIsNotNone(re.search(r"<ContentTypeId>179343</ContentTypeId>", xml))
        self.assertIsNotNone(re.search(r"<Title>EboksTest</Title>", xml))
        self.assertIsNotNone(re.search(r"<FileExtension>pdf</FileExtension>", xml))

    def test_generate_xml_invalid(self):
        with self.assertRaises(ValueError, msg="cpr/cvr must be all digits"):
            EboksMessage.generate_xml("1234567A", "EboksTest", 179343, self.data)
        with self.assertRaises(
            ValueError, msg="unknown recipient type for: {123456789}"
        ):
            EboksMessage.generate_xml("123456789", "EboksTest", 179343, self.data)


@override_settings(EBOKS=EboksTest.test_settings())
class FinalStatusTest(EboksTest):

    @classmethod
    def mock_request(cls, message_id, post_status):
        mock = MagicMock()

        def side_effect(method, url, params, data, **kwargs):
            client_id = settings.EBOKS["client_id"]
            if (
                method == "GET"
                and url == f"https://eboxtest.nanoq.gl/rest/messages/{client_id}/"
                and "abcdefgh" in params["message_id"]
            ):

                return cls.mock_response(
                    200,
                    json.dumps(
                        [
                            {
                                "message_id": message_id,
                                "proxy_response_code": 200,
                                "proxy_error": None,
                                "modified_at": timezone.now().isoformat(),
                                "recipients": [
                                    {
                                        "nr": "12345678",
                                        "recipient_type": "V",
                                        "nationality": "DK",
                                        "status": "exempt",
                                        "reject_reason": None,
                                        "post_processing_status": post_status,
                                    }
                                ],
                            }
                        ]
                    ).encode("utf-8"),
                )
            return cls.mock_response(404)

        mock.side_effect = side_effect
        return mock

    @patch.object(requests.sessions.Session, "request")
    def test_update_final_statuses(self, mock_request):
        message = EboksMessage(
            cpr_cvr="12345678",
            title="EboksTest",
            content_type=179343,
        )
        message.message_id = "abcdefgh"
        message.set_pdf_data(self.data)
        message.status = "post_processing"
        message.recipient_status = "exempt"
        message.post_processing_status = "pending"
        message.is_postprocessing = True
        message.save()

        mock_request.side_effect = self.mock_request(
            message.message_id, "remote printed"
        )
        core_call_command("eboks_update_status")
        message.refresh_from_db()
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.post_processing_status, "remote printed")
        self.assertFalse(message.is_postprocessing)

    @patch.object(requests.sessions.Session, "request")
    def test_update_final_statuses_still_processing(self, mock_request):
        message = EboksMessage(
            cpr_cvr="12345678",
            title="EboksTest",
            content_type=179343,
        )
        message.message_id = "abcdefgh"
        message.set_pdf_data(self.data)
        message.status = "post_processing"
        message.recipient_status = "exempt"
        message.post_processing_status = "pending"
        message.is_postprocessing = True
        message.save()

        mock_request.side_effect = self.mock_request(message.message_id, "pending")
        with EboksClient.from_settings() as client:
            EboksMessage.update_final_statuses(client)
        message.refresh_from_db()
        self.assertEqual(message.status, "post_processing")
        self.assertEqual(message.post_processing_status, "pending")
        self.assertTrue(message.is_postprocessing)

    @patch.object(requests.sessions.Session, "request")
    def test_update_final_statuses_none(self, mock_request):
        # Not initializing anything
        core_call_command("eboks_update_status")
        mock_request.assert_not_called()

    @patch.object(requests.sessions.Session, "request")
    def test_update_final_statuses_already_processed(self, mock_request):
        message = EboksMessage(
            cpr_cvr="12345678",
            title="EboksTest",
            content_type=179343,
        )
        message.message_id = "abcdefgh"
        message.set_pdf_data(self.data)
        message.status = "sent"
        message.recipient_status = "exempt"
        message.post_processing_status = "remote printed"
        message.is_postprocessing = False
        message.save()

        with EboksClient.from_settings() as client:
            EboksMessage.update_final_statuses(client)
        mock_request.assert_not_called()
        message.refresh_from_db()
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.post_processing_status, "remote printed")
        self.assertFalse(message.is_postprocessing)


@override_settings(EBOKS=EboksTest.test_settings())
class ClientInfoTest(EboksTest):

    @staticmethod
    def mock_request(fails=0):
        mock = MagicMock()

        def side_effect(method, url, params, data, **kwargs):
            if mock.fails > 0:
                mock.fails -= 1
                raise ConnectionError
            m = re.search(r"/rest/client/([^/]+)/", url)
            if m is None:
                raise Exception("No match")
            client_id = m.group(1)

            response = Response()
            response.status_code = 200
            response._content = json.dumps(
                {
                    "id": client_id,
                    "enable": True,
                    "name": "TestSystem",
                    "organisational_path": "test/testsystem",
                }
            ).encode("utf-8")
            return response

        mock.fails = fails
        mock.side_effect = side_effect
        return mock

    @patch.object(requests.sessions.Session, "request")
    def test_get_client_info_success(self, mock_request):
        mock_request.side_effect = self.mock_request()
        client = EboksClient.from_settings()
        response = client.get_client_info()
        self.assertEqual(response.status_code, 200)
        client_info = response.json()
        self.assertIsInstance(client_info, dict)
        self.assertEqual(client_info["name"], "TestSystem")
        self.assertEqual(client_info["organisational_path"], "test/testsystem")
        self.assertEqual(client_info["enable"], True)
        self.assertEqual(client_info["id"], "99")


@override_settings(EBOKS=EboksTest.test_settings())
class ClientTest(EboksTest):

    def test_missing_files(self):
        with self.settings(EBOKS=self.test_settings(client_cert="/non-existent-file")):
            with self.assertRaises(FileNotFoundError):
                EboksClient.from_settings()
        with self.settings(EBOKS=self.test_settings(client_key="/non-existent-file")):
            with self.assertRaises(FileNotFoundError):
                EboksClient.from_settings()

    def test_verify(self):
        with self.settings(
            EBOKS={
                **settings.EBOKS,
                "host_verify": "/server.crt",
            }
        ):
            client = EboksClient.from_settings()
            self.assertEqual(client.verify, "/server.crt")
            self.assertEqual(client.session.verify, "/server.crt")


@override_settings(EBOKS=EboksTest.test_settings())
class SuilaMessageTest(EboksTest):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person, _ = Person.objects.update_or_create(
            cpr="0101011111", location_code=1
        )
        cls.year = Year.objects.create(year=2020)
        cls.person_year, _ = PersonYear.objects.update_or_create(
            person=cls.person,
            year=Year.objects.get(year=2020),
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        cls.person_months = [
            PersonMonth.objects.create(
                person_year=cls.person_year,
                month=i,
                benefit_calculated=i,
                import_date=date(2020, 1, 1),
            )
            for i in range(1, 13)
        ]
        cls.message1 = SuilaEboksMessage.objects.create(
            person_month=cls.person_months[0], type="opgørelse"
        )
        cls.message2 = SuilaEboksMessage.objects.create(
            person_month=cls.person_months[0], type="afventer"
        )

    def test_title(self):
        self.assertEqual(self.message1.month, 1)
        self.assertEqual(self.message1.title, "Suila-tapit udbetaling for januar")
        self.assertEqual(self.message2.month, 1)
        self.assertEqual(self.message2.title, "Suila-tapit udbetaling for januar")

    def test_content_type(self):
        self.assertEqual(self.message1.content_type, settings.EBOKS["content_type_id"])
        self.assertEqual(self.message2.content_type, settings.EBOKS["content_type_id"])

    def test_pdf(self):
        self.assertTrue(len(self.message1.pdf) > 0)

    @patch.object(requests.sessions.Session, "request")
    def test_send(self, mock_request):
        mock_request.side_effect = self.mock_request("", "")

        with EboksClient.from_settings() as client:
            self.message1.send(client)
        self.assertIsNotNone(self.message1.sent)

        mock_request.assert_called_with(
            "PUT",
            f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
            f"dispatchsystem/3994/dispatches/{self.message1.message_id}",
            None,
            self.message1.xml,
            timeout=60,
        )
        self.assertEqual(self.message1.status, "sent")
        self.assertEqual(self.message1.recipient_status, "")
        self.assertIsNotNone(self.message1.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_update_welcome_letter(self, mock_request):
        self.message1.update_welcome_letter()
        self.assertIsNone(self.person.welcome_letter)
        mock_request.side_effect = self.mock_request("", "")
        with EboksClient.from_settings() as client:
            self.message1.send(client)
        self.message1.update_welcome_letter()
        self.assertEqual(self.person.welcome_letter, self.message1)
        self.assertTrue(
            self.person.welcome_letter_sent_at > timezone.now() - timedelta(seconds=1)
        )


class EboksManagementCommandTestMixin:

    def quarantine_df(self, in_quarantine):
        return pd.DataFrame(
            [in_quarantine],
            index=["0101011111"],
            columns=["in_quarantine"],
        )

    def setUpMocks(self):
        self.quarantine_patcher = patch("common.utils.get_people_in_quarantine")
        self.submit_patcher = patch(
            "suila.management.commands.send_eboks.ThreadPoolExecutor.submit"
        )
        self.eboks_client_patcher = patch(
            "suila.management.commands.send_eboks.EboksClient"
        )

        self.submit_mock = self.submit_patcher.start()
        self.quarantine_mock = self.quarantine_patcher.start()
        self.eboks_client_mock = self.eboks_client_patcher.start()

        self.addCleanup(self.submit_patcher.stop)
        self.addCleanup(self.quarantine_patcher.stop)
        self.addCleanup(self.eboks_client_patcher.stop)

        # Mock the quarantine dataframe. By default a person is NOT in quarantine
        self.quarantine_mock.return_value = self.quarantine_df(False)

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

        # Setup mock e-Boks client
        self.recipients = [{"status": "ok", "post_processing_status": ""}]
        self.send_message_response = MagicMock()
        self.send_message_response.json.return_value = {
            "recipients": self.recipients,
            "message_id": 666,
        }

        self.client_mock = MagicMock()
        self.client_mock.get_message_id.return_value = 666
        self.client_mock.send_message.return_value = self.send_message_response

        # Patch the factory method to return the mocked client
        self.eboks_client_mock.from_settings.return_value = self.client_mock


class ManagementCommandTest(TransactionTestCase, EboksManagementCommandTestMixin):
    def setUp(self):
        super().setUp()

        self.person, _ = Person.objects.update_or_create(
            cpr="0101011111", location_code=1, full_address="Polarvej 1, 6666 Nuuk"
        )
        self.year = Year.objects.create(year=2020)
        self.person_year = PersonYear.objects.create(
            person=self.person,
            year=self.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        self.period = TaxInformationPeriod.objects.create(
            person_year=self.person_year,
            tax_scope="FULL",
            start_date=datetime(
                self.year.year, 1, 1, tzinfo=timezone.get_current_timezone()
            ),
            end_date=datetime(
                self.year.year, 12, 31, tzinfo=timezone.get_current_timezone()
            ),
        )
        self.person_months = [
            PersonMonth.objects.create(
                person_year=self.person_year,
                month=i,
                benefit_calculated=i,
                import_date=date(2020, 1, 1),
            )
            for i in range(1, 13)
        ]
        self.setUpMocks()
        self.stdout = StringIO()

        try:
            os.remove("/tmp/0101011111.pdf")
        except FileNotFoundError:
            pass

    def call_command(self, year=2020, month=3, *args, **kwargs):
        core_call_command(
            ManagementCommands.SEND_EBOKS,
            year,
            month,
            *args,
            stdout=self.stdout,
            **kwargs,
        )

    def test_management_command(self):
        self.call_command(send=True)

        message = SuilaEboksMessage.objects.get(cpr_cvr="0101011111")
        self.client_mock.send_message.assert_called()
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.type, "opgørelse")

    def test_person_in_quarantine(self):
        self.quarantine_mock.return_value = self.quarantine_df(True)
        self.call_command(send=True)

        message = SuilaEboksMessage.objects.get(cpr_cvr="0101011111")
        self.client_mock.send_message.assert_called()
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.type, "afventer")

    def test_person_not_in_mandtal(self):
        # Arrange: remove tax information period for person year under test
        self.period.delete()
        # Act
        self.call_command(send=True)
        # Assert: no message was created or sent
        self.client_mock.send_message.assert_not_called()
        self.assertFalse(
            SuilaEboksMessage.objects.filter(cpr_cvr="0101011111").exists()
        )

    def test_person_already_received_welcome_letter(self):
        self.call_command(month=3, send=True)

        self.person.refresh_from_db()
        self.assertTrue(self.person.welcome_letter_sent_at is not None)

        self.call_command(month=4, send=True)

        message = SuilaEboksMessage.objects.get(cpr_cvr="0101011111")
        self.client_mock.send_message.assert_called_once()
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.type, "opgørelse")

    def test_bogus_addresses(self):
        for address in [
            "Administrativ kontor, hvor vi laver administrative ting",
            "",
            "0",
            "postkode 9999",
            "Ukendt vej",
            None,
        ]:
            self.person.full_address = address
            self.person.save()
            self.call_command(send=True)
            self.client_mock.send_message.assert_not_called()

    def test_cpr_arg(self):
        self.call_command(send=True, cpr="123")
        self.client_mock.send_message.assert_not_called()

        self.call_command(send=True, cpr="0101011111")
        self.client_mock.send_message.assert_called_once()

    def test_send_arg(self):
        self.call_command(send=False)
        self.client_mock.send_message.assert_not_called()

        self.call_command()  # "send" is False by default
        self.client_mock.send_message.assert_not_called()

        self.call_command(send=True)
        self.client_mock.send_message.assert_called()

    def test_save_arg(self):
        self.call_command(send=False)
        self.assertNotIn("0101011111.pdf", os.listdir("/tmp"))

        self.call_command(send=False, save=True)
        self.assertIn("0101011111.pdf", os.listdir("/tmp"))

    def test_nonexisting_person_month(self):
        PersonMonth.objects.get(month=3).delete()
        self.call_command(month=3, send=True)
        self.client_mock.send_message.assert_not_called()
