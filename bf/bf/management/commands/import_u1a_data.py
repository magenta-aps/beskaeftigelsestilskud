# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import datetime
import logging
import time
from typing import Optional, Tuple

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from bf.akap import AKAPU1A, AKAPU1AItem, get_akap_u1a_entries, get_akap_u1a_items
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
        dry = kwargs.get("dry", False)
        year = kwargs.get("year", None)
        cpr = kwargs.get("cpr", None)

        result: Optional[ImportResult] = None
        try:
            if not year and not cpr:
                logger.info("Importing: All entries")
                result = self._import_everything()
            elif year and not cpr:
                logger.info(f"Importing: Entries from year: {year}")
                result = self._import_year(int(year))
            elif not year and cpr:
                logger.info(f"Importing: Entries by CPR: {cpr}")
                result = self._import_cpr(cpr)
            elif year and cpr:
                logger.info(f"Importing: Entries by CPR: {cpr}, from year: {year}")
                pass
            else:
                logger.warning(
                    f"import_u1a_data called with invalid arguments: {kwargs}"
                )

            if dry:
                transaction.set_rollback(True)
                logger.info("Dry run complete. All changes rolled back.")
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

    # Import logic

    def _import_everything(self) -> ImportResult:
        result = ImportResult()

        akap_u1as = get_akap_u1a_entries(
            settings.AKAP_HOST,  # type: ignore[misc]
            settings.AKAP_API_SECRET,  # type: ignore[misc]
            fetch_all=True,
        )

        for u1a in akap_u1as:
            db_u1a_entry, u1a_created = self._create_or_update_u1a(u1a)
            if u1a_created:
                result.new_entries += 1
            else:
                result.updated_entries += 1

            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

            for u1a_item in u1a.items:
                _, u1a_item_created = self._create_or_update_u1a_item(
                    db_u1a_entry.id, u1a_item
                )
                if u1a_item_created:
                    result.new_items += 1
                else:
                    result.updated_items += 1

        return result

    def _import_year(self, year: int) -> ImportResult:
        result = ImportResult()

        akap_u1as = get_akap_u1a_entries(
            settings.AKAP_HOST,  # type: ignore[misc]
            settings.AKAP_API_SECRET,  # type: ignore[misc]
            year=year,
            fetch_all=True,
        )

        for u1a in akap_u1as:
            db_u1a_entry, u1a_created = self._create_or_update_u1a(u1a)
            if u1a_created:
                result.new_entries += 1
            else:
                result.updated_entries += 1

            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

            for u1a_item in u1a.items:
                _, u1a_item_created = self._create_or_update_u1a_item(
                    db_u1a_entry.id, u1a_item
                )
                if u1a_item_created:
                    result.new_items += 1
                else:
                    result.updated_items += 1

        return result

    def _import_cpr(self, cpr: str) -> ImportResult:
        result = ImportResult()

        akap_u1as = get_akap_u1a_entries(
            settings.AKAP_HOST,  # type: ignore[misc]
            settings.AKAP_API_SECRET,  # type: ignore[misc]
            cpr=cpr,
            fetch_all=True,
        )

        for u1a in akap_u1as:
            db_u1a_entry, u1a_created = self._create_or_update_u1a(u1a)
            if u1a_created:
                result.new_entries += 1
            else:
                result.updated_entries += 1

            u1a.items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                u1a.id,
                fetch_all=True,
            )

            for u1a_item in u1a.items:
                _, u1a_item_created = self._create_or_update_u1a_item(
                    db_u1a_entry.id, u1a_item
                )
                if u1a_item_created:
                    result.new_items += 1
                else:
                    result.updated_items += 1
        return result

    # Create & Update logic

    def _create_or_update_u1a(self, akap_u1a: AKAPU1A) -> Tuple[U1AEntry, bool]:
        qs_current_u1a_entry = U1AEntry.objects.filter(u1a_id=akap_u1a.id)
        if qs_current_u1a_entry.exists():
            qs_current_u1a_entry.update(**akap_u1a.model_dict)
            return U1AEntry.objects.get(u1a_id=akap_u1a.id), 0

        return U1AEntry.objects.create(**akap_u1a.model_dict), 1

    def _create_or_update_u1a_item(
        self, db_u1a_entry_id: int, akap_u1a_item: AKAPU1AItem
    ) -> Tuple[U1AItemEntry, bool]:
        qs_u1a_item_current = U1AItemEntry.objects.filter(u1a_item_id=akap_u1a_item.id)
        if qs_u1a_item_current.exists():
            qs_u1a_item_current.update(
                **{**akap_u1a_item.model_dict, "u1a_entry_id": db_u1a_entry_id}
            )
            return U1AItemEntry.objects.get(u1a_item_id=akap_u1a_item.id), 0

        return (
            U1AItemEntry.objects.create(
                **{**akap_u1a_item.model_dict, "u1a_entry_id": db_u1a_entry_id}
            ),
            1,
        )
