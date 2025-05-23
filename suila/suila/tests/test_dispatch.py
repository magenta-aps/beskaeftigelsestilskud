# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase

from suila.dispatch import JobDispatcher
from suila.exceptions import DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices


class TestJobDispatcher(TestCase):

    @classmethod
    def setUpTestData(cls):
        JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.SUCCEEDED,
            cpr_param="111",
            year_param=2025,
            month_param=1,
        )
        JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.SUCCEEDED,
            cpr_param="222",
            year_param=2025,
            month_param=1,
        )

        JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE,
            status=StatusChoices.FAILED,
            cpr_param="333",
            year_param=2025,
            month_param=1,
        )

        cls.job_dispatcher = JobDispatcher(year=2025, month=1, day=1)

    def test_job_ran_this_year(self):
        self.assertTrue(
            self.job_dispatcher.job_ran_this_year(
                ManagementCommands.CALCULATE_STABILITY_SCORE
            )
        )
        self.assertFalse(
            self.job_dispatcher.job_ran_this_year(ManagementCommands.LOAD_ESKAT)
        )

        next_year = (datetime.datetime.today().year + 1) % 12
        future_job_dispatcher = JobDispatcher(year=next_year)

        self.assertFalse(
            future_job_dispatcher.job_ran_this_year(
                ManagementCommands.CALCULATE_STABILITY_SCORE
            )
        )

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

    @mock.patch("suila.dispatch.management")
    def test_call_job(self, management_mock):

        self.job_dispatcher.check_dependencies = MagicMock()
        self.job_dispatcher.allow_job = MagicMock()
        self.job_dispatcher.allow_job.return_value = False

        self.job_dispatcher.call_job("foo", "die", mucki="bar")
        management_mock.assert_not_called()

        self.job_dispatcher.allow_job.return_value = True
        self.job_dispatcher.call_job("foo", "die", mucki="bar")

        management_mock.call_command.assert_called_once_with(
            "foo",
            "die",
            mucki="bar",
            traceback=False,
            reraise=False,
        )

    def allow_job(self, name, year, month, day, job_ran_this_month=False):

        job_dispatcher = JobDispatcher(day=day, month=month, year=year)

        job_dispatcher.job_ran_this_month = MagicMock()
        job_dispatcher.job_ran_this_month.return_value = job_ran_this_month

        return job_dispatcher.allow_job(name)
