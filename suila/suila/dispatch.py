# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import logging
from typing import Optional

from django.core import management
from django.db.models import Q
from django.utils import timezone

from suila.benefit import get_calculation_date, get_prisme_date
from suila.exceptions import DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices

logger = logging.getLogger(__name__)


class JobDispatcher:
    def __init__(self, day=None, month=None, year=None, reraise=False):
        today = timezone.now()
        self.year = year or today.year
        self.month = month or today.month
        self.day = day or today.day
        self.reraise = reraise

        self.calculation_date = get_calculation_date(self.year, self.month)
        self.prisme_date = get_prisme_date(self.year, self.month)

        self.dependencies = {
            ManagementCommands.CALCULATE_STABILITY_SCORE: [],
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: [],
            ManagementCommands.LOAD_ESKAT: [],
            ManagementCommands.LOAD_PRISME_B_TAX: [],
            ManagementCommands.IMPORT_U1A_DATA: [],
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO: [
                ManagementCommands.LOAD_ESKAT,
            ],
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
            ManagementCommands.SEND_EBOKS: [
                ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
            ],
        }

    def job_ran_this_month(self, name):
        return self.job_ran_month(name, self.month)

    def job_ran_month(self, name: str, month: int):
        return JobLog.objects.filter(
            Q(month_param=month) | Q(month_param=None),
            name=name,
            status=StatusChoices.SUCCEEDED,
            year_param=self.year,
        ).exists()

    def job_ran_this_year(self, name):
        return self.job_ran_year(name, self.year)

    def job_ran_year(self, name: str, year: int):
        return JobLog.objects.filter(
            name=name,
            status=StatusChoices.SUCCEEDED,
            year_param=year,
        ).exists()

    def check_dependencies(self, name):
        dependencies = self.dependencies[name]

        for dependency in dependencies:
            job_ran_this_month = self.job_ran_this_month(dependency)
            if not job_ran_this_month:
                raise DependenciesNotMet(name, dependency)

    def allow_job(
        self, name, year: Optional[int] = None, month: Optional[int] = None
    ) -> bool:
        """
        Determine whether to run a job or not
        """
        job_ran_this_year = (
            self.job_ran_this_year(name) if not year else self.job_ran_year(name, year)
        )
        job_ran_this_month = (
            self.job_ran_this_month(name)
            if not month
            else self.job_ran_month(name, month)
        )

        if name in [
            ManagementCommands.CALCULATE_STABILITY_SCORE,
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
        ]:
            if (
                self.month == 3
                and self.day < self.calculation_date.day
                and not job_ran_this_year
            ):
                return True

        elif name in [
            ManagementCommands.LOAD_ESKAT,
            ManagementCommands.LOAD_PRISME_B_TAX,
            ManagementCommands.IMPORT_U1A_DATA,
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            ManagementCommands.ESTIMATE_INCOME,
        ]:
            return True

        elif name == ManagementCommands.CALCULATE_BENEFIT:
            if (
                self.calculation_date.day <= self.day < self.prisme_date.day
                and not job_ran_this_month
            ):
                return True

        elif name == ManagementCommands.EXPORT_BENEFITS_TO_PRISME:  # pragma: no branch
            if self.day >= self.prisme_date.day and not job_ran_this_month:
                return True

        elif name == ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS:
            if month is not None:
                if self.job_ran_month(
                    ManagementCommands.EXPORT_BENEFITS_TO_PRISME, month
                ):
                    return True

        return False

    def call_job(self, name, *args, **kwargs):
        allow_job_kwargs = {}
        if name in [
            ManagementCommands.CALCULATE_STABILITY_SCORE,
        ]:
            allow_job_kwargs["year"] = args[0]

        if not self.allow_job(name, **allow_job_kwargs):
            return

        self.check_dependencies(name)

        logger.info(
            f"\n{datetime.date(self.year, self.month, self.day)}: "
            f"Running job {name} ..."
        )

        management.call_command(
            name,
            *args,
            traceback=self.reraise,
            reraise=self.reraise,
            **kwargs,
        )
