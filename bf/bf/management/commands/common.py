# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import os
from cProfile import Profile

from django.core.management.base import BaseCommand

from bf.models import JobLog, StatusChoices


class BfBaseCommand(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--profile", action="store_true", default=False)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        available_job_params = [
            f.name for f in JobLog._meta.fields if f.name.endswith("_param")
        ]

        job_kwargs = {
            param: options.get(param.replace("_param", ""))
            for param in available_job_params
        }

        job_log = JobLog.objects.create(
            name=os.path.basename(self.filename).split(".")[0], **job_kwargs
        )

        try:
            if options.get("profile", False):
                profiler = Profile()
                profiler.runcall(self._handle, *args, **options)
                profiler.print_stats(sort="tottime")
            else:
                self._handle(*args, **options)
            job_log.status = StatusChoices.SUCCEEDED
        except:  # noqa: E722
            job_log.status = StatusChoices.FAILED
        finally:
            job_log.save(update_fields=("status",))
