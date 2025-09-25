# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import calendar
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import ANY, MagicMock, call, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from suila.benefit import get_calculation_date, get_eboks_date
from suila.management.commands.common import SuilaBaseCommand
from suila.management.commands.job_dispatcher import Command as JobDispatcherCommand
from suila.models import (
    ManagementCommands,
    Person,
    PersonMonth,
    PersonYear,
    StandardWorkBenefitCalculationMethod,
    StatusChoices,
    Year,
)


class TestJobDispatcherCommands(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.command = JobDispatcherCommand()
        self.command.stdout = StringIO()

        self.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )

        self.year = Year.objects.create(year=2025, calculation_method=self.calc)
        self.person = Person.objects.create(cpr="0101011234", name="Ozzy")
        self.person_year = PersonYear.objects.create(year=self.year, person=self.person)

        for month in range(1, 13):
            PersonMonth.objects.create(
                month=month, person_year=self.person_year, import_date=date.today()
            )

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
                    test_date.year - 1,
                    test_date.month - 2 + 12,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
            ]
            mock_call_command.assert_has_calls(expected_calls, any_order=True)
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
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
                    year=test_date.year,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.SEND_EBOKS,
                    test_date.year - 1,
                    test_date.month - 2 + 12,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
            ]

            mock_call_command.assert_has_calls(expected_calls, any_order=True)
            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.reset_mock()

        with self.subTest("Test February 2025 AGAIN"):
            test_date = get_eboks_date(2025, 2) + timedelta(days=1)
            self._call_job_dispatcher_on_date(test_date, mock_timezone_now)
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
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.LOAD_ESKAT,
                        test_date.year,
                        "monthlyincome",
                        month=None,
                        cpr=None,
                        skew=False,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                        stdout=ANY,
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
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.LOAD_PRISME_B_TAX,
                        test_date.year,
                        test_date.month,
                        traceback=False,
                        reraise=False,
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.IMPORT_U1A_DATA,
                        year=test_date.year,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                        stdout=ANY,
                    ),
                    # Estimation-jobs
                    call(
                        ManagementCommands.ESTIMATE_INCOME,
                        year=test_date.year,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.CALCULATE_BENEFIT,
                        test_date.year,
                        test_date.month - 2,
                        cpr=None,
                        verbosity=1,
                        traceback=False,
                        reraise=False,
                        stdout=ANY,
                    ),
                    call(
                        ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
                        year=test_date.year,
                        month=test_date.month - 2,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                        stdout=ANY,
                    ),
                ]

            if day == eboks_date.day:
                expected_calls += [
                    call(
                        ManagementCommands.SEND_EBOKS,
                        test_date.year,
                        test_date.month - 2,
                        traceback=False,
                        reraise=False,
                        verbosity=1,
                        stdout=ANY,
                    ),
                ]

            # Assert job-calls
            # NOTE: Daily jobs are invoked every day AFTER the "other jobs"
            expected_calls += [
                call(
                    ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS,
                    traceback=False,
                    reraise=False,
                    verbosity=1,
                    stdout=ANY,
                ),
                call(
                    ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
                    verbosity=1,
                    traceback=False,
                    reraise=False,
                    stdout=ANY,
                ),
            ]

            self.assertEqual(mock_call_command.call_count, len(expected_calls))
            mock_call_command.assert_has_calls(expected_calls, any_order=True)
            mock_call_command.reset_mock()

    def run_job_dispatcher(
        self,
        mock_call_command,
        mock_timezone_now,
        calculate_benefit_for_single_cpr=False,
    ):

        # Test data
        test_date = timezone.datetime(2025, 5, 1)
        calculation_date = get_calculation_date(test_date.year, test_date.month)
        _, num_days = calendar.monthrange(test_date.year, test_date.month)

        # Mocking
        mock_call_command.side_effect = _mock_call_command

        day = calculation_date.day

        # Go through each day of the month and verify the correct jobs was
        # called on each day

        # Mock/Change the current date/now
        mock_timezone_now.return_value = timezone.datetime(
            test_date.year, test_date.month, day, 2, 0, 0
        )

        # Run calculate_benefit for a single cpr number
        if calculate_benefit_for_single_cpr:
            call_command(
                ManagementCommands.CALCULATE_BENEFIT, 2025, 3, cpr=self.person.cpr
            )

        # Invoke the job dispatcher command
        call_command(
            self.command,
            year=test_date.year,
            month=test_date.month,
            day=day,
        )

        return [c.args[0] for c in mock_call_command.call_args_list]

    @patch("suila.dispatch.timezone.now")
    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_calculate_benefit_when_benefit_was_not_calculated_for_single_person(
        self, mock_call_command: MagicMock, mock_timezone_now: MagicMock
    ):
        calls = self.run_job_dispatcher(
            mock_call_command,
            mock_timezone_now,
        )
        self.assertIn(ManagementCommands.CALCULATE_BENEFIT, calls)

    @patch("suila.dispatch.timezone.now")
    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_calculate_benefit_when_benefit_was_calculated_for_single_person(
        self, mock_call_command: MagicMock, mock_timezone_now: MagicMock
    ):
        calls = self.run_job_dispatcher(
            mock_call_command,
            mock_timezone_now,
            calculate_benefit_for_single_cpr=True,
        )
        self.assertIn(ManagementCommands.CALCULATE_BENEFIT, calls)

    @patch("suila.dispatch.timezone.now")
    @patch("suila.dispatch.management.call_command")
    @override_settings(ESKAT_BASE_URL="http://djangotest")
    def test_that_job_dispatcher_stops_if_there_are_no_new_btax_files(
        self,
        mock_call_command: MagicMock,
        mock_timezone_now: MagicMock,
    ):
        calculation_date = get_calculation_date(2025, 7)

        def mock_call_command_btax(command_name, *args, **options):
            if (
                timezone.now().day <= calculation_date.day
                and command_name == ManagementCommands.LOAD_PRISME_B_TAX
            ):
                # Simulate that there are no btax files on the calculation date
                raise FileNotFoundError("No Btax files!")
            else:
                # But the next day, there are files
                return _mock_call_command(command_name, *args, **options)

        def run_dispatcher(day):
            mock_call_command.reset_mock()
            mock_timezone_now.return_value = timezone.datetime(
                calculation_date.year,
                calculation_date.month,
                day,
                2,
                0,
                0,
            )
            try:
                call_command(
                    self.command,
                    year=calculation_date.year,
                    month=calculation_date.month,
                    day=day,
                )
            except CommandError:
                # We expect a CommandError only if there are no new b-tax files.
                # We ignore it because we are interested in the calls made to
                # mock_call_command. Not in the error itself.
                pass
            calls = [c.args[0] for c in mock_call_command.call_args_list]
            return calls

        # Mocking
        mock_call_command.side_effect = mock_call_command_btax

        # Validate that we do not calculate / estimate when the btax command fails
        calls = run_dispatcher(calculation_date.day)
        self.assertNotIn(ManagementCommands.CALCULATE_BENEFIT, calls)
        self.assertNotIn(ManagementCommands.ESTIMATE_INCOME, calls)

        # Validate that we do calculate / estimate the next day
        # (when the proper files have appeared)
        calls = run_dispatcher(calculation_date.day + 1)
        self.assertIn(ManagementCommands.CALCULATE_BENEFIT, calls)
        self.assertIn(ManagementCommands.ESTIMATE_INCOME, calls)

        # Validate that we do not run the Btax command the next-next day
        # (we already ran it this month)
        calls = run_dispatcher(calculation_date.day + 2)
        self.assertNotIn(ManagementCommands.LOAD_PRISME_B_TAX, calls)
        self.assertNotIn(ManagementCommands.CALCULATE_BENEFIT, calls)
        self.assertNotIn(ManagementCommands.ESTIMATE_INCOME, calls)

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
