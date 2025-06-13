# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import calendar
from datetime import date, timedelta
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import get_calculation_date, get_eboks_date
from suila.management.commands.common import SuilaBaseCommand
from suila.management.commands.job_dispatcher import Command as JobDispatcherCommand
from suila.models import ManagementCommands, StatusChoices


class TestJobDispatcherCommands(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.command = JobDispatcherCommand()
        self.command.stdout = StringIO()

    @patch("suila.dispatch.timezone.now")
    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_call_stability_score_and_estimation_engine(
        self, mock_call_command: MagicMock, mock_timezone_now: MagicMock
    ):
        mock_call_command.side_effect = _mock_call_command

        with self.subTest("Test Janaruary 2025"):
            test_date = get_eboks_date(2025, 1) + timedelta(days=1)

            # Run the calculations jobs for the month to mimic a more realistic flow
            self._call_job_dispatcher_on_date(
                get_calculation_date(test_date.year, test_date.month),
                mock_timezone_now,
            )
            mock_call_command.reset_mock()

            # Call the jobs on EBOKS day
            self._call_job_dispatcher_on_date(test_date, mock_timezone_now)
            expected_calls = [
                call(
                    ManagementCommands.SEND_EBOKS,
                    year=test_date.year - 1,
                    month=test_date.month - 2 + 12,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
            ]

            mock_call_command.assert_has_calls(expected_calls)
            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.reset_mock()

        with self.subTest("Test February 2025"):
            test_date = get_eboks_date(2025, 2) + timedelta(days=1)

            # Run the calculations jobs for the month to mimic a more realistic flow
            self._call_job_dispatcher_on_date(
                get_calculation_date(test_date.year, test_date.month),
                mock_timezone_now,
            )
            mock_call_command.reset_mock()

            # Call the jobs on EBOKS day
            self._call_job_dispatcher_on_date(test_date, mock_timezone_now)
            expected_calls = [
                call(
                    ManagementCommands.CALCULATE_STABILITY_SCORE,
                    test_date.year - 1,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
                    year=test_date.year,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                ),
                call(
                    ManagementCommands.SEND_EBOKS,
                    year=test_date.year - 1,
                    month=test_date.month - 2 + 12,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                ),
            ]

            mock_call_command.assert_has_calls(expected_calls)
            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.reset_mock()

        with self.subTest("Test February 2025 AGAIN"):
            test_date = get_eboks_date(2025, 2) + timedelta(days=1)

            self._call_job_dispatcher_on_date(test_date, mock_timezone_now)

            mock_call_command.assert_has_calls([])
            self.assertEqual(mock_call_command.call_count, 0)
            mock_call_command.reset_mock()

    @patch("suila.management.commands.job_dispatcher.JobDispatcher")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_verbose(self, job_dispatcher: MagicMock):
        stdout = StringIO()
        stderr = StringIO()

        job_dispatcher_mock = MagicMock()
        job_dispatcher_mock.month = 6
        job_dispatcher_mock.year = 2025
        job_dispatcher.return_value = job_dispatcher_mock

        call_command(
            self.command,
            year=2022,
            month=1,
            day=1,
            verbosity=1,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertNotIn("Done", stdout.getvalue())

        call_command(
            self.command,
            year=2022,
            month=1,
            day=1,
            verbosity=3,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertIn("Done", stdout.getvalue())

    @patch("suila.management.commands.job_dispatcher.JobDispatcher")
    @override_settings(ESKAT_BASE_URL=None)
    def test_job_dispatch_missing_eskat_url(self, job_dispatcher: MagicMock):
        stdout = StringIO()
        stderr = StringIO()

        job_dispatcher_mock = MagicMock()
        job_dispatcher_mock.month = 6
        job_dispatcher_mock.year = 2025
        job_dispatcher.return_value = job_dispatcher_mock

        call_command(
            self.command,
            year=2022,
            month=1,
            day=1,
            verbosity=3,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertIn("ESKAT_BASE_URL is not set", stdout.getvalue())

    # NEW TESTS - after it was decided the job dispatcher will run every day (again)

    @patch("suila.dispatch.timezone.now")
    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_monthly_runs(
        self, mock_call_command: MagicMock, mock_timezone_now: MagicMock
    ):
        # Test data
        test_date = timezone.datetime(2025, 5, 1)
        calculation_date = get_calculation_date(test_date.year, test_date.month)
        eboks_date = get_eboks_date(test_date.year, test_date.month)
        _, num_days = calendar.monthrange(test_date.year, test_date.month)

        # Mocking
        mock_call_command.side_effect = _mock_call_command

        # Go through each day of the month and verify the correct jobs was
        # called on each day
        for day in range(1, num_days + 1):
            # Mock/Change the current date/now for each day
            mock_timezone_now.return_value = timezone.datetime(
                test_date.year, test_date.month, day, 2, 0, 0
            )

            # Invoke the job dispatcher command
            call_command(
                self.command,
                year=test_date.year,
                month=test_date.month,
                day=day,
            )

            # Expect more calls on specific dates
            expected_calls = []
            if day == calculation_date.day:
                expected_calls += [
                    # "data load"-jobs
                    call(
                        ManagementCommands.LOAD_ESKAT,
                        test_date.year,
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
                        test_date.year,
                        "monthlyincome",
                        month=test_date.month,
                        cpr=None,
                        skew=True,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                    ),
                    call(
                        ManagementCommands.LOAD_ESKAT,
                        test_date.year,
                        "taxinformation",
                        month=None,
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
                        year=test_date.year,
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
                        year=test_date.year,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                    ),
                    call(
                        ManagementCommands.CALCULATE_BENEFIT,
                        test_date.year,
                        test_date.month - 2,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                    ),
                    call(
                        ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
                        year=test_date.year,
                        month=test_date.month - 2,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                    ),
                ]

            if day == eboks_date.day:
                expected_calls += [
                    call(
                        ManagementCommands.SEND_EBOKS,
                        year=test_date.year,
                        month=test_date.month - 2,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                    ),
                ]

            # Assert job-calls
            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.assert_has_calls(expected_calls)
            mock_call_command.reset_mock()

    # Helper methods
    def _call_job_dispatcher_on_date(
        self, calc_date: date, mock_timezone_now: MagicMock
    ):
        mock_timezone_now.return_value = timezone.datetime(
            calc_date.year,
            calc_date.month,
            calc_date.day,
            2,
            0,
            0,
        )

        call_command(
            self.command,
            year=calc_date.year,
            month=calc_date.month,
            day=calc_date.day,
        )


# Shared mocking method(s)
def _mock_call_command(command_name, *args, **options):
    now = timezone.now()
    options["status"] = StatusChoices.SUCCEEDED

    # Handlign of command kwargs - since we don't trigger the "argument parser"
    # NOTE: Django management-command concept adds the "args" to the "kwargs" variable
    if command_name in [
        ManagementCommands.LOAD_ESKAT,
        ManagementCommands.CALCULATE_STABILITY_SCORE,
    ]:
        options["year"] = args[0]

    if command_name == ManagementCommands.LOAD_ESKAT:
        options["type"] = args[1]

    joblog = SuilaBaseCommand.create_joblog(command_name, **options)
    joblog.runtime = now
    joblog.runtime_end = now + timedelta(seconds=30)
    joblog.save()
