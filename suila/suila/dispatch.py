# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from common.utils import get_payout_date
from django.conf import settings
from django.core import management
from django.utils import timezone

from suila.exceptions import DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices


class JobDispatcher:
    def __init__(self, day=None, month=None, year=None):
        today = timezone.now()
        self.year = year or today.year
        self.month = month or today.month
        self.day = day or today.day

        self.payout_date = get_payout_date(self.year, self.month)

        # Allow for a week between calculation and payout
        self.calculation_date = self.payout_date - datetime.timedelta(days=7)

        # We send data to prisme "x" days before the payout date
        self.prisme_date = self.payout_date - datetime.timedelta(
            days=settings.PRISME_DELAY
        )

        self.dependencies = {
            ManagementCommands.CALCULATE_STABILITY_SCORE: [],
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: [],
            ManagementCommands.LOAD_ESKAT: [],
            ManagementCommands.ESTIMATE_INCOME: [
                ManagementCommands.LOAD_ESKAT,
            ],
            ManagementCommands.CALCULATE_BENEFIT: [
                ManagementCommands.LOAD_ESKAT,
                ManagementCommands.ESTIMATE_INCOME,
            ],
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME: [
                ManagementCommands.LOAD_ESKAT,
                ManagementCommands.ESTIMATE_INCOME,
                ManagementCommands.CALCULATE_BENEFIT,
            ],
        }

    def job_ran_this_month(self, name):
        return JobLog.objects.filter(
            name=name, status=StatusChoices.SUCCEEDED, year=self.year, month=self.month
        ).exists()

    def job_ran_this_year(self, name):
        return JobLog.objects.filter(
            name=name, status=StatusChoices.SUCCEEDED, year=self.year
        ).exists()

    def check_dependencies(self, name):
        dependencies = self.dependencies[name]

        for dependency in dependencies:
            job_ran_this_month = self.job_ran_this_month(dependency)
            if not job_ran_this_month:
                raise DependenciesNotMet(name, dependency)

    def allow_job(self, name) -> bool:
        """
        Determine whether to run a job or not
        """
        job_ran_this_month = self.job_ran_this_month(name)
        job_ran_this_year = self.job_ran_this_year(name)

        if name in [
            ManagementCommands.CALCULATE_STABILITY_SCORE,
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
        ]:
            if (
                self.month == 1
                and self.day < self.calculation_date.day
                and not job_ran_this_year
            ):
                return True

        elif name in [
            ManagementCommands.LOAD_ESKAT,
            ManagementCommands.ESTIMATE_INCOME,
        ]:
            return True

        elif name == ManagementCommands.CALCULATE_BENEFIT:
            if (
                self.day >= self.calculation_date.day
                and self.day < self.prisme_date.day
                and not job_ran_this_month
            ):
                return True

        elif name == ManagementCommands.EXPORT_BENEFITS_TO_PRISME:  # pragma: no branch
            if self.day >= self.prisme_date.day and not job_ran_this_month:
                return True

        return False

    def call_job(self, name, *args, **kwargs):
        if self.allow_job(name):
            self.check_dependencies(name)
            management.call_command(name, *args, **kwargs)
