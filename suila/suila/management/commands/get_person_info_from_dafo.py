# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Tuple

from requests.exceptions import HTTPError

from suila.integrations.pitu.client import PituClient
from suila.management.commands.common import SuilaBaseCommand
from suila.models import Person


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--maxworkers", type=int, default=5)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Person objects based on CPR data from DAFO/Pitu"""
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading CPR data from database ...")
        if kwargs["cpr"]:
            persons = Person.objects.filter(cpr=kwargs["cpr"])
            if not persons:
                self._write_verbose(
                    f"Could not find any persons with CPR={kwargs['cpr']}"
                )
        else:
            persons = Person.objects.all()

        pitu_client = self._get_pitu_client()

        def fetch_person(person: Person) -> Tuple[Person, Any] | None:
            try:
                return person, pitu_client.get_person_info(person.cpr)
            except HTTPError as e:
                if e.response.status_code == 404:
                    self._write_verbose(
                        f"Could not find person with CPR={person.cpr} in DAFO"
                    )
                else:
                    self._write_verbose(
                        (
                            f"Unexpected {e.response.status_code} "
                            f"error: {str(e.response.content)}"
                        )
                    )
                return None  # Indicate failure

        maxworkers: int = kwargs["maxworkers"]
        self._write_verbose(f"Starting person update-workers (max_worker={maxworkers})")
        with ThreadPoolExecutor(max_workers=maxworkers) as executor:
            future_to_person = {
                executor.submit(fetch_person, person): person for person in persons
            }

            for future in as_completed(future_to_person):
                try:
                    future_tuple = future.result()
                    if not future_tuple:
                        continue

                    person_model, fetched_person_data = future_tuple

                    if "civilstand" in fetched_person_data:
                        person_model.civil_state = fetched_person_data["civilstand"]
                    else:
                        self._write_verbose(
                            f'no "civilstand" in person_data: {fetched_person_data}'
                        )

                    if "myndighedskode" in fetched_person_data:
                        person_model.location_code = fetched_person_data[
                            "myndighedskode"
                        ]
                    else:
                        self._write_verbose(
                            f'no "myndighedskode" in person_data: {fetched_person_data}'
                        )

                    if (
                        "fornavn" in fetched_person_data
                        and "efternavn" in fetched_person_data
                    ):
                        person_model.name = (
                            f"{fetched_person_data['fornavn']} "
                            f"{fetched_person_data['efternavn']}"
                        )
                    else:
                        self._write_verbose(
                            (
                                'no "fornavn" and "efternavn" in '
                                f"person_data: {fetched_person_data}"
                            )
                        )

                    address = fetched_person_data.get("adresse")
                    city = fetched_person_data.get("bynavn")
                    post_code = fetched_person_data.get("postnummer")

                    if all(val is not None for val in (address, city, post_code)):
                        person_model.full_address = f"{address}, {post_code} {city}"

                    person_model.save()

                    self._write_verbose(
                        (
                            f"Updated CPR data for {person_model.cpr} "
                            f"(person data = {fetched_person_data})"
                        )
                    )
                except Exception as e:
                    self._write_verbose(f"Error processing person: {e}")

        self._write_verbose("Done")
        pitu_client.close()

    def _get_pitu_client(self) -> PituClient:
        # Use default configuration (CPR service) for Pitu client
        return PituClient.from_settings()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)
