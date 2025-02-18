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
        """
        Loops over all persons and populates civil_state and location_code
        """
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading location code and civil state from DAFO")
        if kwargs["cpr"]:
            persons = Person.objects.filter(
                cpr=kwargs["cpr"],
            )

            if not persons:
                self._write_verbose(
                    f"Could not find any persons with CPR={kwargs['cpr']}"
                )
        else:
            persons = Person.objects.all()

        pitu_client = PituClient.from_settings()
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

                if "stedkode" in person_data:
                    person.location_code = person_data["stedkode"]
                else:
                    self._write_verbose(f'no "stedkode" in person_data: {person_data}')

                person.save()
                self._write_verbose(
                    f"Updated civil state and location code for {person.cpr}"
                    f"(person data = {person_data})"
                )

        self._write_verbose("Done")
        pitu_client.close()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
