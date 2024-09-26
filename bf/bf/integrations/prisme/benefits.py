# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Generator

from django.conf import settings
from django.db import transaction
from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr
from tenQ.client import ClientException, put_file_in_prisme_folder
from tenQ.writer.g68 import TransaktionstypeEnum, UdbetalingsberettigetIdentKodeEnum

from bf.integrations.prisme.g68g69 import G68G69TransactionPair, G68G69TransactionWriter
from bf.models import PersonMonth, PrismeBatch, PrismeBatchItem

logger = logging.getLogger(__name__)


class BatchExport:
    def __init__(self, year: int, month: int):
        self._year = year
        self._month = month
        self._prisme_settings: dict = settings.PRISME  # type: ignore[misc]

    def get_person_month_queryset(self) -> QuerySet[PersonMonth]:
        # Find all person months for this year/month which:
        # - have not yet been exported,
        # - and have a non-zero calculated benefit
        qs: QuerySet[PersonMonth] = (
            PersonMonth.objects.select_related("person_year__person", "prismebatchitem")
            .filter(
                person_year__year=self._year,
                month=self._month,
                prismebatchitem__isnull=True,
                benefit_paid__isnull=False,
            )
            .exclude(benefit_paid=Decimal("0"))
        )
        # Annotate with string version of CPR (zero-padded to 10 digits)
        qs = qs.annotate(
            identifier=LPad(
                Cast("person_year__person__cpr", CharField()),
                10,
                Value("0"),
            )
        )
        # Annotate with prefix (first two digits of CPR)
        qs = qs.annotate(prefix=Substr("identifier", 1, 2))
        # Order by prefix and CPR
        qs = qs.order_by("prefix", "person_year__person__cpr")
        return qs

    def get_batches(
        self, qs: QuerySet[PersonMonth]
    ) -> Generator[tuple[PrismeBatch, QuerySet[PersonMonth]], None, None]:
        # Split `PersonMonth` queryset into batches, yielding one `PrismeBatch` and the
        # matching `PersonMonth` objects for each `prefix` (== first two digits of CPR.)
        current_batch: PrismeBatch | None = None
        for person_month in qs:
            person_month_prefix: int = int(
                person_month.prefix  # type: ignore[attr-defined]
            )
            if (current_batch is None) or (person_month_prefix != current_batch.prefix):
                current_batch = PrismeBatch(
                    prefix=person_month_prefix,
                    # TODO: should this be passed in from the management command?
                    export_date=date.today(),
                )
                yield (
                    current_batch,
                    qs.filter(prefix=person_month.prefix),  # type: ignore[attr-defined]
                )

    def get_prisme_batch_item(
        self,
        prisme_batch: PrismeBatch,
        person_month: PersonMonth,
        writer: G68G69TransactionWriter,
    ) -> PrismeBatchItem:
        transaction_pair: G68G69TransactionPair = writer.serialize_transaction_pair(
            TransaktionstypeEnum.AndenDestinationTilladt,
            UdbetalingsberettigetIdentKodeEnum.CPR,
            person_month.identifier,  # type: ignore[attr-defined]
            person_month.benefit_paid,  # type: ignore[arg-type]
            date.today(),  # TODO: use calculated date
            date.today(),  # TODO: use calculated date
            "Some descriptive text",  # TODO: generate proper text
        )
        return PrismeBatchItem(
            prisme_batch=prisme_batch,
            person_month=person_month,
            g68_content=transaction_pair.g68,
            g69_content=transaction_pair.g69,
        )

    def upload_batch(
        self,
        prisme_batch: PrismeBatch,
        prisme_batch_items: list[PrismeBatchItem],
    ) -> None:
        # Export batch to Prisme
        buf: BytesIO = BytesIO()
        for prisme_batch_item in prisme_batch_items:
            buf.write(prisme_batch_item.g68_content.encode("utf-8"))
            buf.write(b"\r\n")
            buf.write(prisme_batch_item.g69_content.encode("utf-8"))
            buf.write(b"\r\n")
        buf.seek(0)

        # TODO: use production or development folder depending on settings (or CLI args)
        destination_folder = self._prisme_settings["dirs"]["development"]

        # TODO: revise filename based on customer input
        filename = (
            f"RES_G68_export_{prisme_batch.prefix}_"
            f"{prisme_batch.export_date.strftime('%Y-%m-%d')}.g68"
        )

        try:
            put_file_in_prisme_folder(
                self._prisme_settings,
                buf,
                destination_folder,
                filename,
            )
        except ClientException as e:
            prisme_batch.status = PrismeBatch.Status.Failed
            prisme_batch.failed_message = str(e)
            logger.exception(
                "failed to upload to Prisme "
                "(destination_folder=%r, destination_filename=%r)",
                destination_folder,
                filename,
            )
        else:
            prisme_batch.status = PrismeBatch.Status.Sent
            prisme_batch.failed_message = ""
        finally:
            prisme_batch.save()

    def get_g68_g69_transaction_writer(self):
        return G68G69TransactionWriter(
            0,
            self._prisme_settings["user_number"],
            self._prisme_settings["machine_id"],
        )

    @transaction.atomic
    def export_batches(self, stdout):
        person_month_queryset: QuerySet[PersonMonth] = self.get_person_month_queryset()

        stdout.write(
            f"Found {person_month_queryset.count()} person months to export ..."
        )

        prisme_batch: PrismeBatch
        person_months: QuerySet[PersonMonth]
        for prisme_batch, person_months in self.get_batches(person_month_queryset):
            # Instantiate a new writer for each Prisme batch
            writer: G68G69TransactionWriter = self.get_g68_g69_transaction_writer()

            # Build all items for this batch
            prisme_batch.save()
            prisme_batch_items: list[PrismeBatchItem] = []
            for person_month in person_months:
                prisme_batch_item: PrismeBatchItem = self.get_prisme_batch_item(
                    prisme_batch,
                    person_month,
                    writer,
                )
                prisme_batch_items.append(prisme_batch_item)

                stdout.write(prisme_batch_item.g68_content)
                stdout.write(prisme_batch_item.g69_content)
                stdout.write("")

            PrismeBatchItem.objects.bulk_create(prisme_batch_items)

            # Export this batch to Prisme
            self.upload_batch(prisme_batch, prisme_batch_items)

            stdout.write(
                f"Uploaded {prisme_batch.pk} (year={self._year}, month={self._month})"
            )
