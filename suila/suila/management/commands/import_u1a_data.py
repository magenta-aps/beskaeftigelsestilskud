# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
import logging
import time

from django.conf import settings
from django.db import transaction

from bf.akap import get_akap_u1a_entries, get_akap_u1a_items
from bf.management.commands.common import BfBaseCommand
from bf.models import U1AEntry, U1AItemEntry

logger = logging.getLogger(__name__)


class Command(BfBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        start = time.time()

        # Parse args
        dry = kwargs["dry"]
        year = kwargs["year"]
        cpr = kwargs["cpr"]

        # LOGIC
        if not year and not cpr:
            self._import_everything(dry)
        elif year and not cpr:
            # TODO: for a specific year, go through all u1a-items
            pass
        elif year and cpr:
            # TODO: for a specific year, go through all u1a-items with a specific CPR
            pass
        elif not year and cpr:
            # TODO: Go through u1a-items with a specific CPR
            pass
        else:
            raise Exception("Unsupported")

        # Finish
        duration = datetime.datetime.fromtimestamp(
            time.time() - start, datetime.timezone.utc
        )
        self.stdout.write(f"Done (took {duration.strftime('%H:%M:%S')})")

    def _import_everything(self, dry: bool = False):
        akap_u1as = get_akap_u1a_entries(
            settings.AKAP_HOST,  # type: ignore[misc]
            settings.AKAP_API_SECRET,  # type: ignore[misc]
            fetch_all=True,
        )

        new_u1a_models = []
        new_u1a_item_models = []
        for u1a in akap_u1as:
            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

            u1a_entry_model: U1AEntry = U1AEntry.objects.create(**u1a.model_dict)
            new_u1a_models.append(u1a_entry_model)

            for u1a_item in u1a.items:
                u1a_item_model = U1AItemEntry.objects.create(
                    **{**u1a_item.model_dict, "u1a_entry_id": u1a_entry_model.id}
                )
                new_u1a_item_models.append(u1a_item_model)

        print("----")
        print(f"new u1a entries: {len(new_u1a_models)}")
        print(f"new u1a item entries: {len(new_u1a_item_models)}")
        print("----")
