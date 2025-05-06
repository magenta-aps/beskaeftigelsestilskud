# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import get_calculation_date, get_prisme_date
from suila.exceptions import DependenciesNotMet
from suila.management.commands.common import SuilaBaseCommand
from suila.management.commands.job_dispatcher import Command as JobDispatcherCommand
from suila.models import ManagementCommands, StatusChoices


class TestJobDispatcherCommands(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.command = JobDispatcherCommand()
        self.command.stdout = StringIO()

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_calls_before_calculation_date(
        self, mock_call_command: MagicMock
    ):
        mock_call_command.side_effect = _mock_call_command

        # Three days before the CALCULATION_DATE
        # OBS: CALCULATION_DATE is, by default, the second monday in the month
        job_dispatcher_test_date = get_calculation_date(2025, 5) - timedelta(days=3)

        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

        self.assertEqual(mock_call_command.call_count, 7)
        mock_call_command.assert_has_calls(
            [
                # "data load"-jobs
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "expectedincome",
                    month=None,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "monthlyincome",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=True,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "taxinformation",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_B_TAX, traceback=False, reraise=False
                ),
                call(
                    ManagementCommands.IMPORT_U1A_DATA,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                # Estimation-jobs
                call(
                    ManagementCommands.ESTIMATE_INCOME,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
            ]
        )

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_calls_on_calculation_date(self, mock_call_command: MagicMock):
        mock_call_command.side_effect = _mock_call_command
        job_dispatcher_test_date = get_calculation_date(2025, 5)
        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

        self.assertEqual(mock_call_command.call_count, 8)
        mock_call_command.assert_has_calls(
            [
                # "data load"-jobs
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "expectedincome",
                    month=None,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "monthlyincome",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=True,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "taxinformation",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_B_TAX, traceback=False, reraise=False
                ),
                call(
                    ManagementCommands.IMPORT_U1A_DATA,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                # Estimation-jobs
                call(
                    ManagementCommands.ESTIMATE_INCOME,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                # Calculation-jobs
                call(
                    ManagementCommands.CALCULATE_BENEFIT,
                    job_dispatcher_test_date.year,
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
            ]
        )

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_calls_after_calculation_date(
        self, mock_call_command: MagicMock
    ):
        mock_call_command.side_effect = _mock_call_command

        # NOTE: The date must be after the following interval:
        # `calculation_date.day <= day < prisme_date.day`
        job_dispatcher_test_date: date = get_prisme_date(2025, 5)
        with self.assertRaises(DependenciesNotMet) as context:
            call_command(
                self.command,
                year=job_dispatcher_test_date.year,
                month=job_dispatcher_test_date.month,
                day=job_dispatcher_test_date.day,
                reraise=True,
            )

        self.assertIn(
            "'calculate_benefit' dependency for 'export_benefits_to_prisme' is not met",
            str(context.exception),
        )

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_call_on_year_first_day(self, mock_call_command: MagicMock):
        mock_call_command.side_effect = _mock_call_command

        job_dispatcher_test_date = datetime(2025, 1, 1)
        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

        self.assertEqual(mock_call_command.call_count, 7)
        mock_call_command.assert_has_calls(
            [
                # "data load"-jobs
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "expectedincome",
                    month=None,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "monthlyincome",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=True,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "taxinformation",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_B_TAX, traceback=False, reraise=False
                ),
                call(
                    ManagementCommands.IMPORT_U1A_DATA,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                # Estimation-jobs
                call(
                    ManagementCommands.ESTIMATE_INCOME,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
            ]
        )

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_call_stability_score_and_estimation_engine(
        self, mock_call_command: MagicMock
    ):
        mock_call_command.side_effect = _mock_call_command

        for job_dispatcher_test_data in [
            (get_calculation_date(2025, 1) - timedelta(days=1), False),
            (get_calculation_date(2025, 2) - timedelta(days=1), False),
            (get_calculation_date(2025, 3) - timedelta(days=1), True),
            (get_calculation_date(2025, 3) - timedelta(days=1), False),
        ]:
            job_dispatcher_test_date, expected_to_run = job_dispatcher_test_data
            call_command(
                self.command,
                year=job_dispatcher_test_date.year,
                month=job_dispatcher_test_date.month,
                day=job_dispatcher_test_date.day,
            )

            expected_calls = [
                # "data load"-jobs
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "expectedincome",
                    month=None,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "monthlyincome",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=True,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_ESKAT,
                    job_dispatcher_test_date.year,
                    "taxinformation",
                    month=job_dispatcher_test_date.month,
                    cpr=None,
                    skew=False,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_B_TAX,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.IMPORT_U1A_DATA,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                # Estimation-jobs
                call(
                    ManagementCommands.ESTIMATE_INCOME,
                    year=job_dispatcher_test_date.year,
                    cpr=None,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
            ]

            if expected_to_run:
                expected_calls = [
                    call(
                        ManagementCommands.CALCULATE_STABILITY_SCORE,
                        job_dispatcher_test_date.year - 1,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                    ),
                    call(
                        ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
                        job_dispatcher_test_date.year,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                    ),
                ] + expected_calls

            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.assert_has_calls(expected_calls)
            mock_call_command.reset_mock()


# Shared mocking method(s)
def _mock_call_command(command_name, *args, **options):
    now = timezone.now()
    options["status"] = StatusChoices.SUCCEEDED
    options["runtime"] = now
    options["runtime_end"] = now + timedelta(seconds=30)

    # Handlign of command kwargs - since we don't trigger the "argument parser"
    # NOTE: Django management-command concept adds the "args" to the "kwargs" variable
    if command_name in [
        ManagementCommands.LOAD_ESKAT,
        ManagementCommands.CALCULATE_STABILITY_SCORE,
        ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
    ]:
        options["year"] = args[0]

    if command_name == ManagementCommands.LOAD_ESKAT:
        options["type"] = args[1]

    SuilaBaseCommand.create_joblog(command_name, **options)
