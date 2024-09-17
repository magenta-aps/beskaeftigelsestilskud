# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from common.pitu import PituClient
from django.core.management.base import BaseCommand
from requests.exceptions import HTTPError

from bf.models import Person


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--cpr", type=int)

    def handle(self, *args, **kwargs):
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
                    continue
            person.civil_state = person_data["civilstand"]
            person.location_code = person_data["stedkode"]
            person.save()

        self._write_verbose("Done")
        pitu_client.close()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)