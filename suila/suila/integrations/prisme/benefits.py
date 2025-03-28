# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from csv import DictWriter
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, TextIOWrapper
from typing import Generator

from dateutil.relativedelta import TU, relativedelta
from django.conf import settings
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import CharField, F, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr
from tenacity import (
    after_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from tenQ.client import ClientException, put_file_in_prisme_folder
from tenQ.writer.g68 import TransaktionstypeEnum, UdbetalingsberettigetIdentKodeEnum

from suila.dates import get_payment_date
from suila.integrations.prisme.g68g69 import (
    G68G69TransactionPair,
    G68G69TransactionWriter,
)
from suila.integrations.prisme.mod11 import validate_mod11
from suila.models import (
    PersonMonth,
    PrismeAccountAlias,
    PrismeBatch,
    PrismeBatchItem,
    TaxScope,
)

logger = logging.getLogger(__name__)


class BatchExport:
    def __init__(self, year: int, month: int):
        self._year = year
        self._month = month

    def get_person_month_queryset(self) -> QuerySet[PersonMonth]:
        # Find all person months for this year/month which:
        # - have not yet been exported,
        # - and have a non-zero calculated benefit
        qs: QuerySet[PersonMonth] = (
            PersonMonth.objects.select_related("person_year__person", "prismebatchitem")
            .filter(
                person_year__year=self._year,
                person_year__tax_scope=TaxScope.FULDT_SKATTEPLIGTIG,
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
        # Keep a separate set of all `PersonMonth` PKs where the CPR does not pass a
        # modulus-11 test. (These will be yielded last.)
        non_mod11_pks: set[int] = {
            person_month.pk
            for person_month in qs
            if not validate_mod11(person_month.identifier)  # type: ignore[attr-defined]
        }

        # Split the remaining `PersonMonth` queryset into batches, yielding one
        # `PrismeBatch` and the matching `PersonMonth` objects for each `prefix`
        # (== first two digits of CPR.)
        remaining_qs: QuerySet[PersonMonth] = qs.exclude(pk__in=non_mod11_pks)
        current_batch: PrismeBatch | None = None
        for person_month in remaining_qs:
            # Use default prefix (first two digits of CPR)
            person_month_prefix: int = int(
                person_month.prefix  # type: ignore[attr-defined]
            )
            # Start a new "normal" batch whenever the prefix changes
            if (current_batch is None) or (person_month_prefix != current_batch.prefix):
                current_batch = PrismeBatch(
                    prefix=person_month_prefix,
                    export_date=date.today(),
                )
                yield (
                    current_batch,
                    remaining_qs.filter(
                        prefix=person_month.prefix  # type: ignore[attr-defined]
                    ),
                )

        # Finally, yield the "special" batch of non-mod11 CPR items, if any exist
        if non_mod11_pks:
            non_mod11_batch = PrismeBatch(prefix=32, export_date=date.today())
            yield non_mod11_batch, qs.filter(pk__in=non_mod11_pks)

    def get_prisme_batch_item(
        self,
        prisme_batch: PrismeBatch,
        person_month: PersonMonth,
        writer: G68G69TransactionWriter,
    ) -> PrismeBatchItem | None:
        # Find Prisme account alias for this municipality and tax year
        location_code: str | None = person_month.person_year.person.location_code
        tax_year: int = person_month.person_year.year.year
        try:
            account_alias = PrismeAccountAlias.objects.get(
                tax_municipality_location_code=location_code,
                tax_year=tax_year,
            )
        except PrismeAccountAlias.DoesNotExist:
            logger.error(
                "No Prisme account alias found for tax municipality location code %r,"
                "tax year %r, person %r",
                location_code,
                tax_year,
                person_month.person_year.person,
            )
            return None

        # Zero-padded CPR (as string)
        cpr = person_month.identifier  # type: ignore[attr-defined]

        # Construct invoice number by concatenating batch ID and line number
        # Line numbers can only be 5 digits, so we use the rest of the available 20
        # digits for the Prisme batch ID.
        invoice_no: str = f"{prisme_batch.pk:015d}{writer.line_no:05d}"

        # Build G68/G69 transaction pair
        transaction_pair: G68G69TransactionPair = writer.serialize_transaction_pair(
            TransaktionstypeEnum.AndenDestinationTilladt,
            UdbetalingsberettigetIdentKodeEnum.CPR,
            cpr,
            int(account_alias.alias),
            person_month.benefit_paid,  # type: ignore[arg-type]
            self.get_payment_date(person_month),
            self.get_posting_date(person_month),
            self.get_posting_text(person_month),
            invoice_no,
            self.get_transaction_text(person_month),
        )

        return PrismeBatchItem(
            prisme_batch=prisme_batch,
            person_month=person_month,
            g68_content=transaction_pair.g68,
            g69_content=transaction_pair.g69,
            invoice_no=invoice_no,
        )

    def get_posting_text(self, person_month: PersonMonth) -> str:
        cpr: str = person_month.identifier  # type: ignore[attr-defined]
        date_formatted: str = person_month.year_month.strftime("%b%y").upper()
        return f"SUILA-TAPIT-{cpr}-{date_formatted}"

    def get_transaction_text(self, person_month: PersonMonth) -> str:
        # Note: this text is intentionally not marked for translation, as we do not
        # know the recipient user's preferred language.
        return "www.suila.gl takuuk"

    def get_destination_folder(self, prisme_batch: PrismeBatch) -> str:
        prisme: dict = settings.PRISME  # type: ignore[misc]
        config_key = (
            "g68g69_export_folder"
            if prisme_batch.prefix < 32
            else "g68g69_export_mod11_folder"
        )
        return prisme[config_key]

    def get_destination_filename(self, prisme_batch: PrismeBatch) -> str:
        return (
            "SUILA_G68_export_"
            f"{prisme_batch.prefix:02}_{self._year}_{self._month:02}.g68"
        )

    def get_payment_date(self, person_month: PersonMonth) -> date:
        # Payment date in Prisme is one day before the "official" payment date.
        # (The "official" payment date is the third Tuesday in the month two months
        # after the month we are exporting.)
        # Note, the payment date in Prisme not necessarily the same as the third Monday
        # in the month.
        return get_payment_date(person_month.year, person_month.month) - timedelta(
            days=1
        )

    def get_posting_date(self, person_month: PersonMonth) -> date:
        # Posting date is the second Tuesday two months after the given `PersonMonth`.
        # E.g. for a `PersonMonth` in February 2025, the posting date is April 8, 2025.
        return person_month.year_month + relativedelta(months=2, weekday=TU(+2))

    def upload_batch(
        self,
        prisme_batch: PrismeBatch,
        prisme_batch_items: list[PrismeBatchItem],
    ) -> None:
        # Get destination folder and filename for this batch
        destination_folder: str = self.get_destination_folder(prisme_batch)
        filename: str = self.get_destination_filename(prisme_batch)

        # Export batch to Prisme
        buf: BytesIO = BytesIO()
        for prisme_batch_item in prisme_batch_items:
            buf.write(prisme_batch_item.g68_content.encode("utf-8"))
            buf.write(b"\r\n")
            buf.write(prisme_batch_item.g69_content.encode("utf-8"))
            buf.write(b"\r\n")
        buf.seek(0)

        try:
            self._put_file_in_prisme_folder(buf, destination_folder, filename)
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

    def get_control_list(self, output: TextIOWrapper) -> TextIOWrapper:
        # Fetch all Prisme batch items created for this year and month
        prisme_batch_items: QuerySet[PrismeBatchItem] = (
            PrismeBatchItem.objects.select_related("person_month__person_year__person")
            .filter(
                person_month__person_year__year=self._year,
                person_month__month=self._month,
            )
            .order_by(
                "person_month__person_year__person__cpr",
                "prisme_batch__prefix",
            )
            .annotate(
                cpr=F("person_month__person_year__person__cpr"),
                amount=F("person_month__benefit_paid"),
            )
        )

        # Write each Prisme batch item to CSV report
        writer: DictWriter = DictWriter(
            output,
            fieldnames=["filnavn", "cpr", "beløb"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "filnavn": self.get_destination_filename(row.prisme_batch),
                    "cpr": row.cpr,  # type: ignore[attr-defined]
                    "beløb": row.amount,  # type: ignore[attr-defined]
                }
                for row in prisme_batch_items
            ]
        )
        output.seek(0)
        return output

    def get_g68_g69_transaction_writer(self):
        return G68G69TransactionWriter(
            0,
            settings.PRISME["user_number"],
            settings.PRISME["machine_id"],
        )

    @retry(
        retry=retry_if_exception_type(ClientException),
        reraise=True,  # raise `ClientException` if final retry attempt fails
        stop=stop_after_attempt(10),
        wait=wait_fixed(1),  # 1 second before retry
        after=after_log(logger, logging.DEBUG),  # log all retry attempts
    )
    def _put_file_in_prisme_folder(
        self,
        buf: BytesIO,
        destination_folder: str,
        filename: str,
    ):
        put_file_in_prisme_folder(
            settings.PRISME,  # type: ignore[misc]
            buf,
            destination_folder,
            filename,
        )

    @transaction.atomic
    def export_batches(self, stdout: OutputWrapper, verbosity: int):
        person_month_queryset: QuerySet[PersonMonth] = self.get_person_month_queryset()

        num_person_months: int = person_month_queryset.count()
        num_batches: int = 0

        stdout.write(
            f"Found {num_person_months} person month(s) to export for "
            f"year={self._year}, month={self._month} ...",
        )

        prisme_batch: PrismeBatch
        person_months: QuerySet[PersonMonth]
        for prisme_batch, person_months in self.get_batches(person_month_queryset):
            # Instantiate a new writer for each Prisme batch, ensuring that the line
            # numbers start from 0, etc.
            writer: G68G69TransactionWriter = self.get_g68_g69_transaction_writer()

            # Ensure the current Prisme batch is saved (so it has a PK)
            prisme_batch.save()

            # Build all items for this batch
            prisme_batch_items: list[PrismeBatchItem] = []
            for person_month in person_months:
                prisme_batch_item: PrismeBatchItem | None = self.get_prisme_batch_item(
                    prisme_batch,
                    person_month,
                    writer,
                )
                if prisme_batch_item is not None:
                    prisme_batch_items.append(prisme_batch_item)
                    if verbosity >= 2:
                        stdout.write(f"{person_month}")
                        stdout.write(prisme_batch_item.g68_content)
                        stdout.write(prisme_batch_item.g69_content)
                        stdout.write()
                else:
                    stdout.write(
                        f"Could not build Prisme batch item for {person_month}"
                    )

            # Save all Prisme batch items belonging to the current batch
            PrismeBatchItem.objects.bulk_create(prisme_batch_items)

            # Export the current batch to Prisme
            self.upload_batch(prisme_batch, prisme_batch_items)

            if verbosity >= 2:
                stdout.write(f"Uploaded batch with pk={prisme_batch.pk}")

            num_batches += 1

        stdout.write(
            f"Exported {num_batches} batch(es) ({num_person_months} person month(s)) "
            f"for year={self._year}, month={self._month}."
        )

        # Write control list CSV file to SFTP
        buf: BytesIO = BytesIO()
        self.get_control_list(TextIOWrapper(buf))  # mutates `buf`
        self._put_file_in_prisme_folder(
            buf,
            settings.PRISME["control_folder"],  # type: ignore[misc]
            f"SUILA_kontrolliste_{self._year}_{self._month:02}.csv",
        )
        stdout.write(
            f"Exported control list for year={self._year}, month={self._month}."
        )
