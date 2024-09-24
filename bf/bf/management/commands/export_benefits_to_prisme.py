# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Generator

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr
from tenQ.client import ClientException, put_file_in_prisme_folder
from tenQ.writer.g68 import (
    G68Transaction,
    G68TransactionWriter,
    Posteringshenvisning,
    TransaktionstypeEnum,
    UdbetalingsberettigetIdentKodeEnum,
)
from tenQ.writer.g69 import G69TransactionWriter

from bf.models import PersonMonth, PrismeBatch, PrismeBatchItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class G68G69TransactionPair:
    g68: str
    g69: str


class G68G69TransactionWriter(G68TransactionWriter):
    def __init__(
        self,
        registreringssted: int,
        organisationsenhed: int,
        maskinnummer: int | None = None,
    ):
        super().__init__(
            registreringssted,
            organisationsenhed,
            maskinnummer=maskinnummer,
        )
        self._g69_transaction_writer = G69TransactionWriter(
            registreringssted,
            organisationsenhed,
        )

    def serialize_transaction_pair(
        self,
        transaction_type: TransaktionstypeEnum,
        recipient_type: UdbetalingsberettigetIdentKodeEnum,
        recipient: str,
        amount: int,
        payment_date: date,
        posting_date: date,
        text: str,
    ) -> G68G69TransactionPair:
        # This also increments `self._line_no`
        g68_transaction_serialized = self.serialize_transaction(
            transaction_type,
            recipient_type,
            recipient,
            amount,
            payment_date,
            posting_date,
            text,
        )

        # Get the G68 "posteringshenvisning" ID
        g68_transaction_fields = list(G68Transaction.parse(g68_transaction_serialized))
        g69_udbetalingshenvisning = None
        for field in g68_transaction_fields:
            if isinstance(field, Posteringshenvisning):
                g69_udbetalingshenvisning = field.val

        # Build the G69 transaction, using:
        # - the G68 "posteringshenvisning" as the "udbetalingshenvisning",
        # - the G68 "maskinnummer" as the "maskinnummer",
        # - the G68 "linjeløbenummer" as the "ekspeditionsløbenummer"
        #   (== `self._line_no`),
        # the G68 "posteringsdato" as the "posteringsdato".
        g69_transaction_serialized = self._g69_transaction_writer.serialize_transaction(
            udbet_henv_nr=int(g69_udbetalingshenvisning),  # type: ignore[arg-type]
            eks_løbenr=self._line_no,
            maskinnr=self.machine_id.val,
            kontonr=123456789,  # TODO: get account number(s)
            deb_kred="K",
            beløb=amount,
            post_dato=posting_date,
        )

        return G68G69TransactionPair(
            g68=g68_transaction_serialized,
            g69=g69_transaction_serialized,
        )


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prisme_settings: dict = settings.PRISME  # type: ignore[misc]

    def handle(self, *args, **options):
        year: int = date.today().year
        month: int = date.today().month
        self.export_batches(year, month)

    def get_person_month_queryset(
        self,
        year: int,
        month: int,
    ) -> QuerySet[PersonMonth]:
        # Find all person months for this year/month which:
        # - have not yet been exported,
        # - and have a non-zero calculated benefit
        qs: QuerySet[PersonMonth] = (
            PersonMonth.objects.select_related("person_year__person", "prismebatchitem")
            .filter(
                person_year__year=year,
                month=month,
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
            if (current_batch is None) or (
                person_month.prefix != current_batch.prefix  # type: ignore
            ):
                current_batch = PrismeBatch(
                    prefix=person_month.prefix,  # type: ignore[attr-defined]
                    export_date=date.today(),
                )
                yield current_batch, qs.filter(prefix=current_batch.prefix)

    def get_prisme_batch_item(
        self,
        prisme_batch: PrismeBatch,
        person_month: PersonMonth,
        writer: G68G69TransactionWriter,
    ) -> PrismeBatchItem:
        transaction_pair: G68G69TransactionPair = writer.serialize_transaction_pair(
            TransaktionstypeEnum.AndenDestinationTilladt,
            UdbetalingsberettigetIdentKodeEnum.CPR,  # TODO: support CVR?
            person_month.identifier,  # type: ignore[attr-defined]
            person_month.benefit_paid,  # type: ignore[arg-type]
            date.today(),
            date.today(),
            "Some descriptive text",
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

        destination_folder = self._prisme_settings["dirs"]["development"]
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
    def export_batches(self, year: int, month: int):
        person_month_queryset: QuerySet[PersonMonth] = self.get_person_month_queryset(
            year, month
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

            PrismeBatchItem.objects.bulk_create(prisme_batch_items)

            # Export this batch to Prisme
            self.upload_batch(prisme_batch, prisme_batch_items)
