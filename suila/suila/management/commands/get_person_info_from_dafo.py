# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Tuple, TypeGuard

from django.db.models import Q
from requests.exceptions import HTTPError

from suila.integrations.pitu.client import PituClient
from suila.management.commands.common import SuilaBaseCommand
from suila.models import Person


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--cpr", type=str)
        parser.add_argument("--force", type=bool, default=False)
        parser.add_argument("--maxworkers", type=int, default=5)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Person objects based on CPR data from DAFO/Pitu"""
        self.force = kwargs["force"]
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading CPR data from database ...")

        person_qs_params = (
            [Q(name=None) | Q(full_address=None) | Q(country_code=None)]
            if not self.force
            else []
        )

        if kwargs["cpr"]:
            persons = Person.objects.filter(*person_qs_params, cpr=kwargs["cpr"])
            if not persons:
                self._write_verbose(
                    f"Could not find any persons with CPR={kwargs['cpr']}"
                )
                return self._write_verbose("Done")
        else:
            persons = Person.objects.filter(*person_qs_params).order_by("pk")
            if not persons.exists():
                self._write_verbose("Could not find any persons in the database.")
                return self._write_verbose("Done")

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
                    if future_tuple:
                        person_model, fetched_person_data = future_tuple
                        self.update_person(person_model, fetched_person_data)
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

    def update_person(self, person: Person, data: Dict[str, Any]):
        if "civilstand" in data:
            person.civil_state = data["civilstand"]
        else:
            self._write_verbose(f'no "civilstand" in person_data: {data}')

        if "fornavn" in data and "efternavn" in data:
            person.name = f"{data['fornavn']} " f"{data['efternavn']}"
        else:
            self._write_verbose(
                ('no "fornavn" and "efternavn" in ' f"person_data: {data}")
            )

        address = data.get("adresse")
        city = data.get("bynavn")
        post_code = data.get("postnummer")

        def not_empty(x: str | Any | None) -> TypeGuard[str]:
            return x is not None and len(str(x).strip()) > 0

        post_code_city = " ".join([str(x) for x in (post_code, city) if not_empty(x)])
        person.full_address = ", ".join(filter(not_empty, [address, post_code_city]))
        person.foreign_address = data.get("udlandsadresse")
        person.country_code = data.get("landekode")
        person.cpr_status = data.get("statuskode")
        person.save()

        self._write_verbose(
            (f"Updated CPR data for {person.cpr} " f"(person data = {data})")
        )
