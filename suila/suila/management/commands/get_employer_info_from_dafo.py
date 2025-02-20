# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from common.pitu import PituClient
from django.conf import settings
from requests.exceptions import HTTPError

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

        pitu_client = self._get_pitu_client()

        for employer in employers:
            try:
                employer_data = pitu_client.get(f"/{employer.cvr}")
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

    def _get_pitu_client(self) -> PituClient:
        pitu_settings: dict = settings.PITU  # type: ignore[misc]
        # Use different value than `PITU_SERVICE` for the `service` kwarg, as
        # `PITU_SERVICE` specifies the CPR service (not CVR.)
        return PituClient(**{**pitu_settings, "service": pitu_settings["cvr_service"]})

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
