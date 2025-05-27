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
                # Allowed to run the day after SEND_EBOKS in february
                month == 2
                and day >= get_eboks_date(year, month).day + 1
            ),
        },
        ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: {
            "type": "yearly",
            "validator": lambda year, month, day: (
                # Allowed to run the day after SEND_EBOKS in february
                month == 2
                and day >= get_eboks_date(year, month).day + 1
            ),
        },
        # "load"-jobs
        ManagementCommands.LOAD_ESKAT: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.LOAD_PRISME_B_TAX: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.IMPORT_U1A_DATA: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.GET_PERSON_INFO_FROM_DAFO: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        # "estimation"-jobs
        ManagementCommands.ESTIMATE_INCOME: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        # "calculation"-jobs
        ManagementCommands.CALCULATE_BENEFIT: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                get_calculation_date(year, month).day
                <= day
                < get_prisme_date(year, month).day
            ),
        },
        # "export"-jobs
        ManagementCommands.EXPORT_BENEFITS_TO_PRISME: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_prisme_date(year, month).day
            ),
        },
        ManagementCommands.SEND_EBOKS: {
            "type": "monthly",
            "validator": lambda year, month, day: (
                day >= get_eboks_date(year, month).day
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
        year: int,
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

    def allow_job(self, name, job_params: Optional[Dict[str, str]] = None) -> bool:
        """
        Determine whether to run a job or not
        """
        if name not in self.jobs:
            return False

        # Handle job based on type
        job_config = self.jobs[name]
        match (job_config["type"]):
            case self.JOB_TYPE_YEARLY:
                return self._allow_job_yearly(name, job_config, self.year, job_params)
            case self.JOB_TYPE_MONTHLY:
                return self._allow_job_monthly(
                    name, job_config, self.year, self.month, job_params
                )

        # Default to "False" if the job-type is inknown
        logger.error(f'error: job {name} have an unknown "type": {job_config["type"]}')
        return False

    def call_job(self, name, *args, **kwargs):
        # Gather job_params
        job_params = {}
        if "year" in kwargs:
            job_params["year_param"] = kwargs["year"]
        if "month" in kwargs:
            job_params["month_param"] = kwargs["month"]
        if "type" in kwargs:
            job_params["type_param"] = kwargs["type"]

        match (name):
            case ManagementCommands.CALCULATE_STABILITY_SCORE:
                job_params["year_param"] = args[0]
            case ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE:
                job_params["year_param"] = args[0]
            case ManagementCommands.LOAD_ESKAT:
                job_params["type_param"] = args[1]

        # Check if the job is allowed to be called
        if not self.allow_job(name, job_params):
            return

        # If allowed, check if job dependencies are met
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

    def _allow_job_yearly(
        self,
        job_name: str,
        job_config: Dict,
        year: int,
        job_params: Optional[Dict[str, str]] = None,
    ):
        if self.job_ran_year(job_name, year, job_params):
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
        job_params: Optional[Dict[str, str]] = None,
    ):
        if self.job_ran_month(job_name, year, month, job_params):
            return False

        job_validator = job_config.get("validator", None)
        if job_validator is None:
            return True

        return job_validator(year, month, self.day)
