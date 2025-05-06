# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
import os
from cProfile import Profile
from datetime import datetime, timezone

from django.core.management import CommandError
from django.core.management.base import BaseCommand

from suila.models import JobLog, StatusChoices

logger = logging.getLogger(__name__)


class SuilaBaseCommand(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("--reraise", action="store_true", default=False)
        super().add_arguments(parser)

    def handle(self, *args, **options):
        job_name = os.path.basename(self.filename).split(".")[0]
        job_log = self.create_joblog(job_name, *args, **options)

        try:
            if options.get("profile", False):
                profiler = Profile()
                profiler.runcall(self._handle, *args, **options)
                profiler.print_stats(sort="tottime")
            else:
                self._handle(*args, **options)
            job_log.status = StatusChoices.SUCCEEDED
        except Exception as exc:
            logger.exception("SuilaBaseCommand error!")
            job_log.status = StatusChoices.FAILED
            if options.get("reraise", False):
                raise exc
            else:
                raise CommandError() from exc
        finally:
            job_log.runtime_end = datetime.now(tz=timezone.utc)
            job_log.save(
                update_fields=(
                    "status",
                    "runtime_end",
                )
            )

    @staticmethod
    def create_joblog(job_name, **kwargs):
        available_job_params = [
            f.name for f in JobLog._meta.fields if f.name.endswith("_param")
        ]

        job_kwargs = {
            param: kwargs.get(param.replace("_param", ""))
            for param in available_job_params
        }

        # Add status to job_kwargs if its in the method-kwargs
        if "status" in kwargs:
            job_kwargs["status"] = kwargs["status"]

        return JobLog.objects.create(name=job_name, **job_kwargs)
