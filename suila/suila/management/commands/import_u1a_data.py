# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
import logging
import time
from typing import Optional

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from bf.akap import get_akap_u1a_entries, get_akap_u1a_items
from bf.management.commands.common import BfBaseCommand
from bf.models import U1AEntry, U1AItemEntry

logger = logging.getLogger(__name__)


class ImportResult(BaseModel):
    new_entries: int = 0
    new_items: int = 0
    updated_entries: int = 0
    updated_items: int = 0


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
        result: Optional[ImportResult] = None
        try:
            if not year and not cpr:
                logger.info("Importing: All entries")
                result = self._import_everything(dry)
            elif year and not cpr:
                logger.info(f"Importing: Entries from {year}")
                pass
            elif not year and cpr:
                logger.info(f"Importing: Entries by {cpr}")
                pass
            elif year and cpr:
                logger.info(f"Importing: Entries by {cpr}, from {year}")
                pass
            else:
                raise Exception("Unsupported")
        except Exception as e:
            logger.exception(
                f"Unknown error occured for import: CPR={cpr}, YEAR={year}"
            )
            raise e

        # Finish
        duration = datetime.datetime.fromtimestamp(
            time.time() - start, datetime.timezone.utc
        )
        logger.info("DONE!")

        logger.info(f"U1AEntries created: {result.new_entries}")
        logger.info(f"U1AEntries updated: {result.updated_entries}")
        logger.info(f"U1AItemEntries created: {result.new_items}")
        logger.info(f"U1AItemEntries updated: {result.updated_items}")

        logger.info(f"Exec time: {duration.strftime('%H:%M:%S')}")

    def _import_everything(self, dry: bool = False) -> ImportResult:
        result = ImportResult()

        akap_u1as = get_akap_u1a_entries(
            settings.AKAP_HOST,  # type: ignore[misc]
            settings.AKAP_API_SECRET,  # type: ignore[misc]
            fetch_all=True,
        )

        for u1a in akap_u1as:
            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

            qs_current_u1a_entry = U1AEntry.objects.filter(u1a_id=u1a.id)
            db_u1a_entry: Optional[U1AEntry] = None
            if qs_current_u1a_entry.exists():
                qs_current_u1a_entry.update(**u1a.model_dict)
                db_u1a_entry = U1AEntry.objects.get(u1a_id=u1a.id)
                result.updated_entries += 1
            else:
                db_u1a_entry = U1AEntry.objects.create(**u1a.model_dict)
                result.new_entries += 1

            for u1a_item in u1a.items:
                qs_u1a_item_current = U1AItemEntry.objects.filter(
                    u1a_item_id=u1a_item.id
                )

                if qs_u1a_item_current.exists():
                    qs_u1a_item_current.update(
                        **{**u1a_item.model_dict, "u1a_entry_id": db_u1a_entry.id}
                    )
                    result.updated_items += 1
                else:
                    U1AItemEntry.objects.create(
                        **{**u1a_item.model_dict, "u1a_entry_id": db_u1a_entry.id}
                    )
                    result.new_items += 1

        return result
