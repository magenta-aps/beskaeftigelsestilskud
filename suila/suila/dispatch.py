# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import logging
from typing import Dict, Optional

from django.core import management
from django.db.models import Q
from django.utils import timezone

from suila.benefit import get_calculation_date, get_eboks_date
from suila.exceptions import ConfigurationError, DependenciesNotMet
from suila.models import JobLog, ManagementCommands, StatusChoices
from suila.types import JOB_NAME, JOB_TYPE

logger = logging.getLogger(__name__)


class JobDispatcher:
    JOB_TYPE_YEARLY: JOB_TYPE = "yearly"
    JOB_TYPE_MONTHLY: JOB_TYPE = "monthly"
    JOB_TYPE_DAILY: JOB_TYPE = "daily"

    jobs: Dict[JOB_NAME, Dict] = {
        # "year"-Jobs
        ManagementCommands.CALCULATE_STABILITY_SCORE: {
            "type": JOB_TYPE_YEARLY,
            "validator": lambda year, month, day: (
                month == 2 and day >= get_eboks_date(year, month).day + 1 or month == 3
            ),
        },
        ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: {
            "type": JOB_TYPE_YEARLY,
            "validator": lambda year, month, day: (
                month == 2 and day >= get_eboks_date(year, month).day + 1 or month == 3
            ),
        },
        # Daily jobs
        ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS: {
            "type": JOB_TYPE_DAILY,
        },
        # "load"-jobs
        ManagementCommands.LOAD_ESKAT: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.LOAD_PRISME_B_TAX: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.IMPORT_U1A_DATA: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.GET_PERSON_INFO_FROM_DAFO: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO: {
            "type": JOB_TYPE_DAILY,
            "validator": lambda year, month, day: (True),
        },
        # "estimation"-jobs
        ManagementCommands.ESTIMATE_INCOME: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        # "calculation"-jobs
        ManagementCommands.CALCULATE_BENEFIT: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        # "export"-jobs
        ManagementCommands.EXPORT_BENEFITS_TO_PRISME: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_calculation_date(year, month).day
            ),
        },
        ManagementCommands.SEND_EBOKS: {
            "type": JOB_TYPE_MONTHLY,
            "validator": lambda year, month, day: (
                day >= get_eboks_date(year, month).day
            ),
        },
    }

    def __init__(self, day=None, month=None, year=None, reraise=False, stdout=None):
        self.now = timezone.now()
        self.year = year or self.now.year
        self.month = month or self.now.month
        self.day = day or self.now.day
        self.reraise = reraise
        self.stdout = stdout

        self.dependencies: dict[JOB_NAME : list[JOB_NAME]] = {
            ManagementCommands.CALCULATE_STABILITY_SCORE: [],
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE: [],
            ManagementCommands.LOAD_ESKAT: [],
            ManagementCommands.LOAD_PRISME_B_TAX: [],
            ManagementCommands.IMPORT_U1A_DATA: [],
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO: [],
            ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO: [],
            ManagementCommands.ESTIMATE_INCOME: [
                ManagementCommands.LOAD_ESKAT,
                ManagementCommands.LOAD_PRISME_B_TAX,
                ManagementCommands.IMPORT_U1A_DATA,
                ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
                ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
            ],
            ManagementCommands.CALCULATE_BENEFIT: [
                ManagementCommands.ESTIMATE_INCOME,
            ],
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME: [
                ManagementCommands.CALCULATE_BENEFIT,
            ],
            ManagementCommands.SEND_EBOKS: [
                ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
            ],
            ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS: [],
        }

        if self.month == 3:
            self.dependencies[ManagementCommands.ESTIMATE_INCOME] += [
                ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE
            ]

    def get_job_ran_filters(
        self, job_name: str, job_params: Optional[Dict[str, str]] = None
    ):
        filters_kwargs = {
            "name": job_name,
            "status": StatusChoices.SUCCEEDED,
        }

        if job_params:
            for job_param_name, job_param_value in job_params.items():
                if not job_param_name.endswith("_param"):
                    continue
                filters_kwargs[job_param_name] = job_param_value

        return filters_kwargs

    def job_ran_month(
        self,
        name: str,
        year: int,
        month: int,
        job_params: Optional[Dict[str, str]] = None,
    ):
        filters_kwargs = self.get_job_ran_filters(name, job_params)
        return JobLog.objects.filter(
            Q(runtime__year=year), Q(runtime__month=month), **filters_kwargs
        ).exists()

    def job_ran_year(
        self, name: str, year: int, job_params: Optional[Dict[str, str]] = None
    ):
        filters_kwargs = self.get_job_ran_filters(name, job_params)
        return JobLog.objects.filter(Q(runtime__year=year), **filters_kwargs).exists()

    def job_ran_day(
        self,
        name: str,
        year: int,
        month: int,
        day: int,
        job_params: Optional[Dict[str, str]] = None,
    ):
        filters_kwargs = self.get_job_ran_filters(name, job_params)
        return JobLog.objects.filter(
            Q(runtime__year=year),
            Q(runtime__month=month),
            Q(runtime__day=day),
            **filters_kwargs,
        ).exists()

    def check_dependencies(self, job_name: JOB_NAME):
        if job_name not in self.dependencies:
            raise ConfigurationError(f"{job_name} is missing in dependency-dict")

        for dependency_job_name in self.dependencies[job_name]:
            job_type: JOB_TYPE = self.jobs[dependency_job_name]["type"]
            if job_type == self.JOB_TYPE_MONTHLY and not self.job_ran_month(
                dependency_job_name, self.year, self.month
            ):
                raise DependenciesNotMet(job_name, dependency_job_name)
            elif job_type == self.JOB_TYPE_YEARLY and not self.job_ran_year(
                dependency_job_name, self.year
            ):
                raise DependenciesNotMet(job_name, dependency_job_name)

    def allow_job(self, name, job_params: Optional[Dict[str, str]] = None) -> bool:
        """
        Determine whether to run a job or not
        """
        if name not in self.jobs:
            return False

        # Verbosity is not relevant when deciding whether to run a job or not
        if job_params:
            job_params.pop("verbosity_param", None)

        # Handle job based on type
        job_config: Dict = self.jobs[name]
        job_config_validator = job_config.get("validator", None)
        match (job_config["type"]):
            case self.JOB_TYPE_YEARLY:
                if self.job_ran_year(name, self.year, job_params):
                    return False
                return (
                    job_config_validator(self.year, self.month, self.day)
                    if job_config_validator
                    else True
                )
            case self.JOB_TYPE_MONTHLY:
                if self.job_ran_month(name, self.year, self.month, job_params):
                    return False
                return (
                    job_config_validator(self.year, self.month, self.day)
                    if job_config_validator
                    else True
                )
            case self.JOB_TYPE_DAILY:
                if self.job_ran_day(name, self.year, self.month, self.day, job_params):
                    return False
                return (
                    job_config_validator(self.year, self.month, self.day)
                    if job_config_validator
                    else True
                )

        # Default to "False" if the job-type is inknown
        logger.error(f'error: job {name} have an unknown "type": {job_config["type"]}')
        return False

    def call_job(self, name, *args, **kwargs):
        # Gather job_params
        job_params = {}

        try:
            for param, value in kwargs.items():
                job_params[param + "_param"] = value

            match (name):
                case ManagementCommands.CALCULATE_STABILITY_SCORE:
                    job_params["year_param"] = args[0]
                case ManagementCommands.LOAD_ESKAT:
                    job_params["type_param"] = args[1]
        except IndexError:
            logger.exception(f"Invalid parameters for job: {name}")
            return

        # Check if the job is allowed to be called
        if not self.allow_job(name, job_params):
            return

        # If allowed, check if job dependencies are met
        try:
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
                stdout=self.stdout,
                **kwargs,
            )
        except DependenciesNotMet as e:
            logger.warning(f"DependencyNotMet exception for job: {name}: {e}")

            # Add joblog object so the job appears in the joblog UI
            JobLog.objects.create(
                name=name, status=StatusChoices.DEPENDENCIES_NOT_MET, output=e
            )
        except ConfigurationError:
            logger.exception(f"ConfigurationError exception for job: {name}")
        except management.CommandError:
            logger.exception(f"CommandError exception for job: {name}")
            # NOTE: We just log these errors, since jobs shouldn't prevent us from
            #       running other jobs through the JobDispatcher afterwards
