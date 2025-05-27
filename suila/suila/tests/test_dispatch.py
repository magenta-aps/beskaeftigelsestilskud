# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
import random
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

    def test_job_ran_this_month(self):
        with self.subTest("current month"):
            self.assertTrue(
                self.job_dispatcher.job_ran_this_month(
                    ManagementCommands.CALCULATE_STABILITY_SCORE
                )
            )
            self.assertFalse(
                self.job_dispatcher.job_ran_this_month(ManagementCommands.LOAD_ESKAT)
            )

        with self.subTest("next month"):
            next_month = (datetime.datetime.today().month + 1) % 12
            future_job_dispatcher = JobDispatcher(
                year=self.job_dispatcher.year, month=next_month, day=1
            )
            self.assertFalse(
                future_job_dispatcher.job_ran_this_month(
                    ManagementCommands.CALCULATE_STABILITY_SCORE
                )
            )

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

    def test_allow_job(self):
        self.assertTrue(
            self.allow_job(ManagementCommands.CALCULATE_STABILITY_SCORE, 2021, 3, 1)
        )
        self.assertFalse(
            self.allow_job(ManagementCommands.CALCULATE_STABILITY_SCORE, 2021, 2, 1)
        )

        self.assertTrue(
            self.allow_job(
                ManagementCommands.LOAD_ESKAT,
                random.randint(2000, 3000),
                random.randint(1, 12),
                random.randint(1, 31),
            )
        )
        self.assertTrue(
            self.allow_job(
                ManagementCommands.ESTIMATE_INCOME,
                random.randint(2000, 3000),
                random.randint(1, 12),
                random.randint(1, 31),
            )
        )

        # 2024-01-08 is "the day before the second tuesday" in january
        self.assertTrue(
            self.allow_job(ManagementCommands.CALCULATE_BENEFIT, 2024, 1, 8)
        )
        self.assertFalse(
            self.allow_job(ManagementCommands.CALCULATE_BENEFIT, 2024, 1, 7)
        )

        self.assertTrue(
            self.allow_job(ManagementCommands.CALCULATE_BENEFIT, 2024, 1, 14)
        )
        self.assertFalse(
            self.allow_job(ManagementCommands.CALCULATE_BENEFIT, 2024, 1, 15)
        )

        # 2024-01-15 is the day before the third tuesday in january
        self.assertTrue(
            self.allow_job(ManagementCommands.EXPORT_BENEFITS_TO_PRISME, 2024, 1, 15)
        )
        self.assertFalse(
            self.allow_job(ManagementCommands.EXPORT_BENEFITS_TO_PRISME, 2024, 1, 14)
        )

        # If the job already ran it should not be run again
        self.assertFalse(
            self.allow_job(
                ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
                2024,
                1,
                15,
                job_ran_this_month=True,
            )
        )
        self.assertFalse(
            self.allow_job(
                ManagementCommands.CALCULATE_BENEFIT,
                2024,
                1,
                9,
                job_ran_this_month=True,
            )
        )

    def test_allow_job_load_prisme_benefits_posting_status(self):
        # Arrange
        job_dispatcher = JobDispatcher(year=2024, month=1, day=15)
        job_dispatcher.job_ran_month = lambda name, month: True
        # Act
        result = job_dispatcher.allow_job(
            ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS,
            year=2025,
            month=1,
        )
        # Assert
        self.assertTrue(result)
