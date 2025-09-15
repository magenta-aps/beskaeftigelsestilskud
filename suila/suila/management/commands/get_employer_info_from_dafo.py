# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from requests.exceptions import HTTPError

from suila.integrations.pitu.client import PituClient
from suila.management.commands.common import SuilaBaseCommand
from suila.models import Employer


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--cvr", type=str)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Employer objects based on CVR data from DAFO/Pitu"""
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading CVR data from DAFO")
        if kwargs["cvr"]:
            employers = Employer.objects.filter(cvr=kwargs["cvr"])
            if not employers:
                self._write_verbose(
                    f"Could not find any employers with CVR={kwargs['cvr']}"
                )
        else:
            employers = Employer.objects.all()

        pitu_client = PituClient.from_settings()

        # TODO: optimize this loop
        # - only update `Employer` objects whose `name` is NULL,
        # - only update `Employer` objects whose last update is older than X months,
        # - parallelize requests to DAFO/Pitu,
        # - look up more than one CVR in each API request, if possible.

        for employer in employers:
            try:
                employer_data = pitu_client.get_company_info(employer.cvr)
            except HTTPError as e:
                if e.response.status_code == 404:
                    self._write_verbose(
                        f"Could not find employer with CVR={employer.cvr} in DAFO"
                    )
                else:
                    self._write_verbose(
                        f"Unexpected {e.response.status_code} error: "
                        f"{e.response.content}"
                    )
            else:
                if "navn" in employer_data:
                    employer.name = employer_data["navn"]
                    employer.save()
                    self._write_verbose(
                        f"Updated name for {employer.cvr} ({employer.name}"
                    )
                else:
                    self._write_verbose(
                        f"No employer name for {employer.cvr} (data={employer_data})"
                    )

        self._write_verbose("Done")
        pitu_client.close()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
