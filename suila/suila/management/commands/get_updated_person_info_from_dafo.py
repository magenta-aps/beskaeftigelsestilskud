# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime

from django.db.models import Q

from suila.management.commands.get_person_info_from_dafo import (
    Command as GetPersonInfoFromDafoCommand,
)
from suila.models import Person


class Command(GetPersonInfoFromDafoCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--since", type=str, required=True)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        """Updates all Person objects based on CPR data from DAFO/Pitu"""
        self.force = kwargs["force"]
        if kwargs["since"]:
            self.since = datetime.fromisoformat(kwargs["since"])
        else:
            self.since = None
        self._verbose = kwargs["verbosity"] > 1
        self._write_verbose("Loading updated CPRS from DAFO ...")
        self.pitu_client = self._get_pitu_client()

        person_qs_params = []
        pitu_client = self._get_pitu_client()
        updated_cprs = pitu_client.get_subscription_results(self.since)
        person_qs_params.append(Q(cpr__in=updated_cprs))

        persons = Person.objects.filter(*person_qs_params).order_by("pk")

        self.update_persons(persons, kwargs["maxworkers"])

        self._write_verbose("Done")
        pitu_client.close()
