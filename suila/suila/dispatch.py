# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import logging
from typing import Dict, Optional

from django.core import management
from django.db.models import Q
from django.utils import timezone

from suila.benefit import get_calculation_date, get_eboks_date, get_prisme_date
from suila.exceptions import DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices

logger = logging.getLogger(__name__)


class JobDispatcher:
    JOB_TYPE_YEARLY = "yearly"
    JOB_TYPE_MONTHLY = "monthly"

    jobs = {
        # "year"-Jobs
        ManagementCommands.CALCULATE_STABILITY_SCORE: {
            "type": "yearly",
            "validator": lambda year, month, day: (
                month == 3 and day < get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: {
            "type": "yearly",
            "validator": lambda year, month, day: (
                month == 3 and day < get_calculation_date(year, month).day
            ),
        },
        # "load"-jobs
        ManagementCommands.LOAD_ESKAT: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day <= now.day
            ),
        },
        ManagementCommands.LOAD_PRISME_B_TAX: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day <= now.day
            ),
        },
        ManagementCommands.IMPORT_U1A_DATA: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day <= now.day
            ),
        },
        ManagementCommands.GET_PERSON_INFO_FROM_DAFO: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day <= now.day
            ),
        },
        # "estimation"-jobs
        ManagementCommands.ESTIMATE_INCOME: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day <= now.day
            ),
        },
        # "calculation"-jobs
        ManagementCommands.CALCULATE_BENEFIT: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                get_calculation_date(year, month).day
                <= now.day
                < get_prisme_date(year, month).day
            ),
        },
        # "export"-jobs
        ManagementCommands.EXPORT_BENEFITS_TO_PRISME: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                now.day >= get_prisme_date(year, month).day
            ),
        },
        ManagementCommands.SEND_EBOKS: {
            "type": "monthly",
            "validator": lambda now, year, month: (
                now.day >= get_eboks_date(year, month).day
            ),
        },
    }

    def __init__(self, day=None, month=None, year=None, reraise=False):
        self.now = timezone.now()
        self.year = year or self.now.year
        self.month = month or self.now.month
        self.day = day or self.now.day
        self.reraise = reraise

        self.calculation_date = get_calculation_date(self.year, self.month)
        self.prisme_date = get_prisme_date(self.year, self.month)
        self.eboks_date = get_eboks_date(self.year, self.month)

        self.dependencies = {
            ManagementCommands.CALCULATE_STABILITY_SCORE: [],
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: [],
            ManagementCommands.LOAD_ESKAT: [],
            ManagementCommands.LOAD_PRISME_B_TAX: [],
            ManagementCommands.IMPORT_U1A_DATA: [],
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO: [],
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
            ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS: [],
        }

    def job_ran_month(
        self,
        name: str,
        year: str,
        month: int,
        job_params: Optional[Dict[str, str]] = None,
    ):
        filters_kwargs = {
            "name": name,
            "status": StatusChoices.SUCCEEDED,
        }

        if job_params:
            for job_param_name, job_param_value in job_params.items():
                if not job_param_name.endswith("_param"):
                    continue
                filters_kwargs[job_param_name] = job_param_value

        return JobLog.objects.filter(
            Q(runtime__year=year), Q(runtime__month=month), **filters_kwargs
        ).exists()

    def job_ran_year(
        self, name: str, year: int, job_params: Optional[Dict[str, str]] = None
    ):
        filters_kwargs = {
            "name": name,
            "status": StatusChoices.SUCCEEDED,
        }

        if job_params:
            for job_param_name, job_param_value in job_params.items():
                if not job_param_name.endswith("_param"):
                    continue
                filters_kwargs[job_param_name] = job_param_value

        return JobLog.objects.filter(Q(runtime__year=year), **filters_kwargs).exists()

    def check_dependencies(self, name):
        for dependency in self.dependencies[name]:
            if not self.job_ran_month(dependency, self.year, self.month):
                raise DependenciesNotMet(name, dependency)

    def allow_job(self, name, *args, **kwargs) -> bool:
        """
        Determine whether to run a job or not
        """
        # Gather job-params
        year = kwargs.get("year", None)
        year = year if year is not None else self.year

        month = kwargs.get("month", None)
        month = month if month is not None else self.month

        type_param = kwargs.get("type", None)

        # Job-param "special cases"
        match (name):
            case ManagementCommands.CALCULATE_STABILITY_SCORE:
                year = args[0]
            case ManagementCommands.LOAD_ESKAT:
                type_param = args[1]

        # Get Job config
        job_config = self.jobs.get(name, None)
        if not job_config:
            return False

        # Handle job based on type
        match (job_config["type"]):
            case self.JOB_TYPE_YEARLY:
                return self._allow_job_yearly(name, job_config, year)
            case self.JOB_TYPE_MONTHLY:
                return self._allow_job_monthly(
                    name, job_config, year, month, type_param
                )

        # Default to "False" if the job-type is inknown
        logger.error(f'error: job {name} have an unknown "type": {job_config["type"]}')
        return False

    def call_job(self, name, *args, **kwargs):
        if not self.allow_job(name, *args, **kwargs):
            return

        try:
            self.check_dependencies(name)
        except DependenciesNotMet:
            logger.warning(f"DependencyNotMet exception for job: {name}")
        else:
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

    def _allow_job_yearly(self, job_name: str, job_config: Dict, year: int):
        job_ran_this_year = self.job_ran_year(job_name, year)

        # Only allow yearly jobs to run once a year
        if job_ran_this_year:
            return False

        job_validator = job_config.get("validator", None)
        if job_validator is None:
            return True

        return job_validator(year, self.month, self.day)

    def _allow_job_monthly(
        self,
        job_name: str,
        job_config: Dict,
        year: int,
        month: int,
        type_param: Optional[str] = None,
    ):
        job_ran_this_month = self.job_ran_month(
            job_name,
            year,
            month,
            job_params={
                "type_param": type_param,
            },
        )

        if job_ran_this_month:
            return False

        job_validator = job_config.get("validator", None)
        if job_validator is None:
            return True

        return job_validator(self.now, self.year, self.month)
