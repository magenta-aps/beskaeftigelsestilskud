# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import get_payout_date
from suila.management.commands.job_dispatcher import Command as JobDispatcherCommand
from suila.models import JobLog, ManagementCommands, StatusChoices


class TestJobDispatcherCommands(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.command = JobDispatcherCommand()
        self.command.stdout = StringIO()

    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_job_dispatch_calls_second_tuesday(self, mock_call_command: MagicMock):
        mock_call_command.side_effect = _mock_call_command

        job_dispatcher_test_date = datetime(2025, 4, 8)
        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

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

        payout_date: date = get_payout_date(2025, 5)
        calculation_date: date = payout_date - timedelta(days=7)
        # FYI: subtraction of 7-days, is currently hardcoded into
        # the JobDispatcher class

        job_dispatcher_test_date = calculation_date
        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

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
    def test_job_dispatch_call_on_year_first_day(self, mock_call_command: MagicMock):
        mock_call_command.side_effect = _mock_call_command

        job_dispatcher_test_date = datetime(2025, 1, 1)
        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

        mock_call_command.assert_has_calls(
            [
                # "once a year"-jobs
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


# Shared mocking method(s)
def _mock_call_command(command_name, *args, **options):
    # Handle command "_param"'s
    cmd_param_year = (
        options.get("year", None) if command_name not in ["load_eskat"] else args[0]
    )

    cmd_param_type = (
        options.get("type", None) if command_name not in ["load_eskat"] else args[1]
    )
    cmd_param_month = options.get("month", None)

    # Create JobLog entry for command
    now = timezone.now()
    JobLog.objects.create(
        name=command_name,
        status=StatusChoices.SUCCEEDED,
        year_param=cmd_param_year,
        month_param=cmd_param_month,
        type_param=cmd_param_type,
        # Fake it took 30 seconds to run the job
        runtime=now,
        runtime_end=now + timedelta(seconds=30),
    )
