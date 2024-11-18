# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
#
# Job which runs all other relevant management jobs on the proper days.
# Intended to be run daily

import datetime

from common.utils import get_payout_date
from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def add_arguments(self, parser):

        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--day", type=int)
        parser.add_argument("--cpr", type=str)

    def handle(self, *args, **options):
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
        today = datetime.date.today()

        day = options["day"] or today.day
        month = options["month"] or today.month
        year = options["year"] or today.year
        cpr = options["cpr"]
        ESKAT_BASE_URL = settings.ESKAT_BASE_URL  # type: ignore[misc]
        PRISME_DELAY = settings.PRISME_DELAY

        # Get the date on which citizens expect their money to be on their accounts.
        payout_date = get_payout_date(year, month)

        # Allow for a week between calculation and payout
        calculation_date = payout_date - datetime.timedelta(days=7)

        # We send data to prisme "x" days before the payout date
        prisme_date = payout_date - datetime.timedelta(days=PRISME_DELAY)

        # Jobs to run once a year (Before the first benefit calculation)
        if month == 1 and day == 1:
            # Calculate stability score
            management.call_command(
                "calculate_stability_score",
                year - 1,
                verbosity=verbosity,
            )

            # Auto-select estimation engine
            management.call_command(
                "autoselect_estimation_engine",
                year,
                verbosity=verbosity,
            )

        for typ in ["expectedincome", "monthlyincome", "taxinformation"]:

            if not ESKAT_BASE_URL:
                self._write_verbose(
                    "ESKAT_BASE_URL is not set - cannot load data from eskat"
                )
                break

            # Load data from eskat
            management.call_command(
                "load_eskat",
                year,
                typ,
                month=None if typ == "expectedincome" else month,
                verbosity=verbosity,
                cpr=cpr,
            )

        # Estimate income
        management.call_command(
            "estimate_income",
            year=year,
            cpr=cpr,
            verbosity=verbosity,
        )

        if day == calculation_date.day:
            # Calculate benefit
            management.call_command(
                "calculate_benefit",
                year,
                month=month,
                cpr=cpr,
                verbosity=verbosity,
            )

        if day == prisme_date.day:
            # Send to prisme
            management.call_command(
                "export_benefits_to_prisme",
                year=year,
                month=month,
                verbosity=verbosity,
            )

        self._write_verbose("Done")

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
