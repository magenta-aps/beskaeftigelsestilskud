# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import get_calculation_date
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

        # Verify the jobs run the day before calculation_date in march
        job_dispatcher_test_date: date = get_calculation_date(2025, 3) - timedelta(
            days=1
        )

        call_command(
            self.command,
            year=job_dispatcher_test_date.year,
            month=job_dispatcher_test_date.month,
            day=job_dispatcher_test_date.day,
        )

        self.assertEqual(mock_call_command.call_count, 9)
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

        # Verify the jobs DON'T RUN before "the day before calculation_date"
        for job_dispatcher_test_date in [
            get_calculation_date(2025, 1) - timedelta(days=1),
            get_calculation_date(2025, 2) - timedelta(days=1),
        ]:
            mock_call_command.reset_mock()
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
            )


# Shared mocking method(s)
def _mock_call_command(command_name, *args, **options):
    now = timezone.now()
    JobLog.objects.create(
        name=command_name,
        status=StatusChoices.SUCCEEDED,
        year_param=(
            options.get("year", None) if command_name not in ["load_eskat"] else args[0]
        ),
        month_param=options.get("month", None),
        type_param=(
            options.get("type", None) if command_name not in ["load_eskat"] else args[1]
        ),
        # Fake it took 30 seconds to run the job
        runtime=now,
        runtime_end=now + timedelta(seconds=30),
    )
