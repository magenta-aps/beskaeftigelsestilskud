# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
from unittest import mock
from unittest.mock import ANY, MagicMock

from django.test import TestCase, override_settings

from suila.dispatch import JobDispatcher
from suila.exceptions import ConfigurationError, DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices


class TestJobDispatcher(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.joblog_succeeded_1 = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.SUCCEEDED,
            cpr_param="111",
            year_param=2025,
            month_param=1,
        )
        cls.joblog_succeeded_1.runtime = datetime.datetime(2025, 1, 1)
        cls.joblog_succeeded_1.save()

        cls.joblog_succeeded_2 = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.SUCCEEDED,
            cpr_param="222",
            year_param=2025,
            month_param=1,
        )
        cls.joblog_succeeded_2.runtime = datetime.datetime(2025, 1, 1)
        cls.joblog_succeeded_2.save()

        cls.joblog_failed_1 = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.FAILED,
            cpr_param="333",
            year_param=2025,
            month_param=1,
        )
        cls.joblog_failed_1.runtime = datetime.datetime(2025, 1, 1)
        cls.joblog_failed_1.save()

        cls.joblog_succeeded_3 = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.SUCCEEDED,
            cpr_param="3334",
            year_param=2025,
            month_param=2,
        )
        cls.joblog_succeeded_3.runtime = datetime.datetime(2025, 2, 1)
        cls.joblog_succeeded_3.save()

        cls.job_dispatcher = JobDispatcher(year=2025, month=1, day=1)

    def test_check_dependencies(self):
        with self.assertRaises(DependenciesNotMet):
            self.job_dispatcher.check_dependencies(
                ManagementCommands.EXPORT_BENEFITS_TO_PRISME
            )

        self.job_dispatcher.dependencies[
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME
        ] = [ManagementCommands.CALCULATE_STABILITY_SCORE]

        self.job_dispatcher.check_dependencies(
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME
        )

    @mock.patch("suila.dispatch.logger")
    @mock.patch("suila.dispatch.management")
    def test_call_job(self, management_mock: MagicMock, mock_logger: MagicMock):
        self.job_dispatcher.check_dependencies = MagicMock()
        self.job_dispatcher.allow_job = MagicMock()

        self.job_dispatcher.allow_job.return_value = False
        self.job_dispatcher.call_job("foo", "die", mucki="bar")
        management_mock.call_command.assert_not_called()

        self.job_dispatcher.allow_job.return_value = True
        self.job_dispatcher.call_job("foo", "die", mucki="bar")
        management_mock.call_command.assert_called_once_with(
            "foo",
            "die",
            mucki="bar",
            traceback=False,
            reraise=False,
            stdout=ANY,
        )
        management_mock.call_command.reset_mock()

        # Cover where the "DependenciesNotMet" exception is raised
        self.job_dispatcher.check_dependencies.side_effect = DependenciesNotMet(
            ManagementCommands.ESTIMATE_INCOME, ManagementCommands.LOAD_ESKAT
        )
        self.job_dispatcher.call_job(ManagementCommands.ESTIMATE_INCOME, year=2025)
        management_mock.call_command.assert_not_called()

        mock_logger.warning.assert_called_once_with(
            (
                "DependencyNotMet exception for job: estimate_income: "
                "'load_eskat' dependency for 'estimate_income' is not met"
            )
        )

    @mock.patch("suila.dispatch.logger")
    @mock.patch("suila.dispatch.management")
    def test_call_job_configuration_error(
        self, management_mock: MagicMock, mock_logger: MagicMock
    ):
        self.job_dispatcher.check_dependencies = MagicMock()
        self.job_dispatcher.allow_job = MagicMock()

        self.job_dispatcher.allow_job.return_value = False
        self.job_dispatcher.call_job("foo", "die", mucki="bar")
        management_mock.call_command.assert_not_called()

        self.job_dispatcher.allow_job.return_value = True
        self.job_dispatcher.call_job("foo", "die", mucki="bar")
        management_mock.call_command.assert_called_once_with(
            "foo",
            "die",
            mucki="bar",
            traceback=False,
            reraise=False,
            stdout=ANY,
        )
        management_mock.call_command.reset_mock()

        self.job_dispatcher.check_dependencies.side_effect = ConfigurationError(
            "she's a maaaniac maaaniac on the floor. Maaniac at your door. Maaniac ...."
        )
        self.job_dispatcher.call_job(ManagementCommands.ESTIMATE_INCOME, year=2025)
        management_mock.call_command.assert_not_called()
        mock_logger.exception.assert_called_once_with(
            "ConfigurationError exception for job: estimate_income"
        )

    def test_job_ran_month(self):
        # Check if a job ran a specific month + verify invalid params don't hinder this
        self.assertTrue(
            self.job_dispatcher.job_ran_month(
                ManagementCommands.CALCULATE_STABILITY_SCORE,
                year=2025,
                month=2,
                job_params={"invalid_attr": "blahblah"},
            )
        )

        # Verify that a valid joblog-field can be used in job_params
        self.assertFalse(
            self.job_dispatcher.job_ran_month(
                ManagementCommands.CALCULATE_STABILITY_SCORE,
                year=2025,
                month=2,
                job_params={"cpr_param": "112233"},
            )
        )

    def test_job_ran_year(self):
        # Check if a job ran a specific year + verify invalid params don't hinder this
        self.assertTrue(
            self.job_dispatcher.job_ran_year(
                ManagementCommands.CALCULATE_STABILITY_SCORE,
                self.job_dispatcher.year,
                job_params={"invalid_attr": "thedarkside", "cpr_param": "3334"},
            )
        )

        self.assertFalse(
            self.job_dispatcher.job_ran_year(
                ManagementCommands.LOAD_ESKAT, self.job_dispatcher.year
            )
        )

        self.assertFalse(
            self.job_dispatcher.job_ran_year(
                ManagementCommands.CALCULATE_STABILITY_SCORE,
                self.job_dispatcher.year + 1,
            )
        )

    def test_allow_job_invalid_job_name(self):
        self.assertFalse(self.job_dispatcher.allow_job("something-darkside"))

    def test_allow_job_invalid_job_type(self):
        self.job_dispatcher.jobs["something-darkside"] = {
            "type": "always",
            "validator": lambda year, month, day: True,
        }

        self.assertFalse(self.job_dispatcher.allow_job("something-darkside"))

    def test_check_dependencies_invalid_job_type(self):
        with self.assertRaises(ConfigurationError):
            self.job_dispatcher.check_dependencies("something-darkside")

    @mock.patch("suila.dispatch.logger")
    @override_settings(ESKAT_BASE_URL=None)
    def test_call_job_cmd_error(self, mock_logger: MagicMock):
        job_dispatcher = JobDispatcher(day=25)  # Pick a day AFTER the calculation date
        job_dispatcher.call_job(ManagementCommands.LOAD_ESKAT, 2025, "monthlyincome")
        mock_logger.exception.assert_called_once_with(
            f"CommandError exception for job: {ManagementCommands.LOAD_ESKAT}"
        )

    @mock.patch("suila.dispatch.logger")
    def test_call_job_params_error(self, mock_logger: MagicMock):
        job_dispatcher = JobDispatcher()
        job_dispatcher.call_job(ManagementCommands.LOAD_ESKAT)
        mock_logger.exception.assert_called_once_with(
            f"Invalid parameters for job: {ManagementCommands.LOAD_ESKAT}"
        )
