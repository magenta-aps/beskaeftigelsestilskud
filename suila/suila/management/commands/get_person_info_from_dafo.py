# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from common.pitu import PituClient
from requests.exceptions import HTTPError

from suila.management.commands.common import SuilaBaseCommand
from suila.models import Person


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Person objects based on CPR data from DAFO/Pitu"""
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading CPR data from DAFO")
        if kwargs["cpr"]:
            persons = Person.objects.filter(cpr=kwargs["cpr"])
            if not persons:
                self._write_verbose(
                    f"Could not find any persons with CPR={kwargs['cpr']}"
                )
        else:
            persons = Person.objects.all()

        pitu_client = self._get_pitu_client()

        for person in persons:
            try:
                person_data = pitu_client.get_person_info(person.cpr)
            except HTTPError as e:
                if e.response.status_code == 404:
                    self._write_verbose(
                        f"Could not find person with CPR={person.cpr} in DAFO"
                    )
                else:
                    self._write_verbose(
                        f"Unexpected {e.response.status_code} error: "
                        f"{e.response.content}"
                    )
            else:
                if "civilstand" in person_data:
                    person.civil_state = person_data["civilstand"]
                else:
                    self._write_verbose(
                        f'no "civilstand" in person_data: {person_data}'
                    )

                if "fornavn" in person_data and "efternavn" in person_data:
                    person.name = f"{person_data['fornavn']} {person_data['efternavn']}"
                else:
                    self._write_verbose(
                        f'no "fornavn" and "efternavn" in person_data: {person_data}'
                    )

                address = person_data.get("adresse")
                city = person_data.get("bynavn")
                post_code = person_data.get("postnummer")
                if all(val is not None for val in (address, city, post_code)):
                    person.full_address = f"{address}, {post_code} {city}"

                person.save()

                self._write_verbose(
                    f"Updated CPR data for {person.cpr} (person data = {person_data})"
                )

        self._write_verbose("Done")
        pitu_client.close()

    def _get_pitu_client(self) -> PituClient:
        # Use default configuration (CPR service) for Pitu client
        return PituClient.from_settings()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
