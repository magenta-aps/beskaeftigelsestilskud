# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import batched
from typing import Any, Dict, List, Tuple

from common.pitu import PituClient
from requests.exceptions import HTTPError
from simple_history.utils import bulk_update_with_history

from suila.management.commands.common import SuilaBaseCommand
from suila.models import Person


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--maxworkers", type=int, default=5)
        parser.add_argument("--batchsize", type=int, default=100)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Person objects based on CPR data from DAFO/Pitu"""
        self._verbose = kwargs["verbosity"] > 1
        maxworkers: int = kwargs["maxworkers"]
        batch_size: int = kwargs["batchsize"]

        # Load the persons from the database
        persons_qs = Person.objects.all()
        if kwargs["cpr"]:
            persons_qs = Person.objects.filter(cpr=kwargs["cpr"])

        # Configure the helper-method which fetches the person from DAFO
        pitu_client = self._get_pitu_client()

        def fetch_person(person: Person) -> Tuple[Person, Any]:
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
                            f"error: {e.response.content}"
                        )
                    )
                return None  # Indicate failure

        self._write_verbose(
            f"Going through persons in batches (batch_size={batch_size}) ..."
        )
        for batch in batched(persons_qs, batch_size):
            self._write_verbose(
                (
                    "Starting ThreadPool to fetch person info from "
                    f"DAFO (max_worker={maxworkers})"
                )
            )

            models_to_update: List[Person] = []
            with ThreadPoolExecutor(max_workers=maxworkers) as executor:
                try:
                    future_to_person = {
                        executor.submit(fetch_person, person): person
                        for person in batch
                    }
                    for future in as_completed(future_to_person):
                        future_tuple = future.result()
                        if not future_tuple:
                            continue

                        person_model, fetched_person_data = future_tuple

                        models_to_update.append(
                            self._update_person(person_model, fetched_person_data)
                        )
                except Exception as e:
                    self._write_verbose(
                        f"Error processing person {person_model.cpr}: {e}"
                    )

            if len(models_to_update) > 0:
                self._write_verbose(
                    (
                        "Updating persons i bulk (nr. of models: "
                        f"{len(models_to_update)})..."
                    )
                )

                bulk_update_with_history(
                    models_to_update,
                    Person,
                    fields=("civil_state", "location_code", "name", "full_address"),
                    batch_size=batch_size,
                )

        self._write_verbose("Done")
        pitu_client.close()

    def _get_pitu_client(self) -> PituClient:
        # Use default configuration (CPR service) for Pitu client
        return PituClient.from_settings()

    def _write_verbose(self, msg, **kwargs):
        if self._verbose:
            self.stdout.write(msg, **kwargs)

    def _update_person(self, person_model: Person, fetched_person_data: Dict):
        if "civilstand" in fetched_person_data:
            person_model.civil_state = fetched_person_data["civilstand"]
        else:
            self._write_verbose(
                f'no "civilstand" in person_data: {fetched_person_data}'
            )

        if "myndighedskode" in fetched_person_data:
            person_model.location_code = fetched_person_data["myndighedskode"]
        else:
            self._write_verbose(
                f'no "myndighedskode" in person_data: {fetched_person_data}'
            )

        if "fornavn" in fetched_person_data and "efternavn" in fetched_person_data:
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

        return person_model
