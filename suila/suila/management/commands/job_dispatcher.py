# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
#
# Job which runs all other relevant management jobs on the proper days.
# Intended to be run daily

from django.conf import settings

from suila.dispatch import JobDispatcher
from suila.management.commands.common import SuilaBaseCommand
from suila.models import ManagementCommands


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--day", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def _handle(self, *args, **options):
        """
        Job which runs all other relevant management jobs on the proper days.

        if run daily the job will execute the following commands:
            - Every year (on the first of January):
                - Calculate stability score
                - autoselect estimation engine
            - Every day:
                - Load data from eskat
                - Estimate yearly income
            - Every month (on the second tuesday):
                - Calculate payout
            - Every month (on day before the third tuesday):
                - Send payouts to PRISME

        Options
        ---------
        day : int
            Day to run the job for. Defaults to today's day
        month : int
            Month to run the job for. Defaults to today's month
        year : int
            Year to run the job for. Defaults to today's year
        cpr : str
            Person to run the job for. Defaults to all persons.

        Notes
        ------------
        This job is intended to be run on a daily cycle using the following management
        command:

        >>> python manage.py job_dispatcher

        If required the day, month and year can be specified when running the job.
        For example: When a job which was supposed to run on Jan 1st 2024 fails,
        you can run it manually using:

        >>> python manage.py job_dispatcher --year=2024 --month=1 --day=1

        Even though you might not be running the job on the first of January, the job
        will still execute all tasks which are supposed to run on the first of january.
        """
        verbosity = options["verbosity"]
        self._verbose = verbosity > 1
        job_dispatcher = JobDispatcher(
            day=options["day"],
            month=options["month"],
            year=options["year"],
            reraise=options["reraise"],
        )

        year = job_dispatcher.year
        month = job_dispatcher.month
        cpr = options["cpr"]
        ESKAT_BASE_URL = settings.ESKAT_BASE_URL  # type: ignore[misc]

        job_dispatcher.call_job(
            ManagementCommands.CALCULATE_STABILITY_SCORE, year - 1, verbosity=verbosity
        )
        job_dispatcher.call_job(
            ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE, year, verbosity=verbosity
        )

        # Call "load_eskat" for 3 different "types"
        for typ in ["expectedincome", "monthlyincome", "taxinformation"]:

            if not ESKAT_BASE_URL:
                self._write_verbose(
                    "ESKAT_BASE_URL is not set - cannot load data from eskat"
                )
                break

            # Load data from eskat
            job_dispatcher.call_job(
                ManagementCommands.LOAD_ESKAT,
                year,
                typ,
                month=None if typ == "expectedincome" else month,
                verbosity=verbosity,
                cpr=cpr,
                skew=typ == "monthlyincome",
            )

        # Populate `Person.location_code` and `Person.civil_state` (requires Pitu/DAFO
        # API access via valid client certificate.)
        job_dispatcher.call_job(
            ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
            cpr=cpr,
            verbosity=verbosity,
        )

        # Estimate income
        job_dispatcher.call_job(
            ManagementCommands.ESTIMATE_INCOME,
            year=year,
            cpr=cpr,
            verbosity=verbosity,
        )

        # Calculate benefit
        job_dispatcher.call_job(
            ManagementCommands.CALCULATE_BENEFIT,
            year,
            month=month,
            cpr=cpr,
            verbosity=verbosity,
        )

        # Send to prisme
        job_dispatcher.call_job(
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
            year=year,
            month=month,
            verbosity=verbosity,
        )

        # Send eboks messages
        job_dispatcher.call_job(
            ManagementCommands.SEND_EBOKS,
            year=year,
            month=month,
            verbosity=verbosity,
        )

        self._write_verbose("Done")
