# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import os
from csv import DictWriter
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Generator

from common.utils import add_or_subtract_working_days
from dateutil.relativedelta import TU, relativedelta
from django.conf import settings
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import CharField, Exists, F, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr
from django.utils.numberformat import format as format_number
from simple_history.utils import bulk_update_with_history
from tenacity import after_log, retry, retry_if_exception_type, stop_after_attempt
from tenQ.client import ClientException, put_file_in_prisme_folder
from tenQ.writer.g68 import TransaktionstypeEnum, UdbetalingsberettigetIdentKodeEnum

from suila.dates import get_payment_date
from suila.integrations.prisme.g68g69 import (
    G68G69TransactionPair,
    G68G69TransactionWriter,
)
from suila.integrations.prisme.mod11 import validate_mod11
from suila.integrations.prisme.retry import retry_wait
from suila.models import (
    PersonMonth,
    PrismeAccountAlias,
    PrismeBatch,
    PrismeBatchItem,
    TaxInformationPeriod,
)

logger = logging.getLogger(__name__)


class BaseExport:
    def get_queryset(self) -> QuerySet:
        raise NotImplementedError("must be defined by subclass")  # pragma: no cover

    def get_prisme_account_alias_lookup(self, obj) -> tuple[str | None, int]:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_posting_text(self, obj) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_transaction_text(self, obj) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_payment_amount(self, obj) -> Decimal | None:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_payment_date(self, obj) -> date:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_posting_date(self, obj) -> date:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_destination_filename(self, prisme_batch: PrismeBatch) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_control_list_data(self) -> QuerySet:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_control_list_filename(self) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def process_prisme_batch_items_on_successful_upload(
        self, prisme_batch_items: list[PrismeBatchItem]
    ) -> None:
        pass  # pragma: no cover

    def print_start_banner(self, stdout, num_objects: int) -> None:
        pass  # pragma: no cover

    def print_success_banner(
        self, stdout, num_objects: int, num_succeeded_batches: int
    ) -> None:
        pass  # pragma: no cover

    def print_failed_banner(self, stdout, num_failed_batches: int):
        pass  # pragma: no cover

    def print_control_list_success_banner(self, stdout):
        pass  # pragma: no cover

    def _get_prisme_batch_item_instance(
        self,
        prisme_batch: PrismeBatch,
        obj,
        transaction_pair,
        invoice_no,
    ) -> PrismeBatchItem:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_batches(
        self, qs: QuerySet
    ) -> Generator[tuple[PrismeBatch, QuerySet], None, None]:
        # Get `mod11_separate_cprs` list of CPRs from settings
        prisme: dict = settings.PRISME  # type: ignore[misc]
        mod11_separate_cprs: list[str] = prisme["mod11_separate_cprs"]

        # Keep a separate set of all object PKs where the CPR does not pass a
        # modulus-11 test. (These will be yielded last.)
        non_mod11_pks: set[int] = {
            obj.pk
            for obj in qs
            if not validate_mod11(obj.identifier)  # type: ignore[attr-defined]
        }

        # Split the remaining queryset into batches, yielding one `PrismeBatch` and its
        # matching objects for each `prefix` (== first two digits of CPR.)
        remaining_qs: QuerySet = qs.exclude(pk__in=non_mod11_pks)
        current_batch: PrismeBatch | None = None
        for obj in remaining_qs:
            # Use default prefix (first two digits of CPR)
            obj_prefix: int = int(obj.prefix)  # type: ignore[attr-defined]
            # Start a new "normal" batch whenever the prefix changes
            if (current_batch is None) or (obj_prefix != current_batch.prefix):
                current_batch = PrismeBatch(
                    prefix=obj_prefix,
                    export_date=date.today(),
                )
                yield (
                    current_batch,
                    remaining_qs.filter(  # type: ignore[misc]
                        prefix=obj.prefix  # type: ignore[attr-defined]
                    ),
                )

        # Finally, yield batches for the non-mod11 CPR items, if any exist
        if non_mod11_pks:
            non_mod11: QuerySet = qs.filter(pk__in=non_mod11_pks)
            if mod11_separate_cprs:
                # Yield separate batch for *each* CPR
                sub_qs: QuerySet = non_mod11.filter(
                    person_year__person__cpr__in=mod11_separate_cprs
                )
                for obj in sub_qs:
                    logger.info(
                        "Yielding separate batch for non-mod11 CPR %r",
                        obj.person_year.person.cpr,
                    )
                    yield (
                        PrismeBatch(
                            # Use the CPR as prefix
                            prefix=int(obj.person_year.person.cpr),
                            export_date=date.today(),
                        ),
                        qs.filter(pk=obj.pk),
                    )

            # Yield a *combined* batch for the non-mod11 CPRs *not in*
            # `mod11_separate_cprs`
            remaining_non_mod11: QuerySet = non_mod11.exclude(
                person_year__person__cpr__in=mod11_separate_cprs
            )
            if remaining_non_mod11.exists():
                yield (
                    PrismeBatch(prefix=32, export_date=date.today()),
                    remaining_non_mod11,
                )

    def get_prisme_batch_item(
        self,
        prisme_batch: PrismeBatch,
        obj,
        writer: G68G69TransactionWriter,
    ) -> PrismeBatchItem | None:
        # Find Prisme account alias for this municipality and tax year
        location_code, tax_year = self.get_prisme_account_alias_lookup(obj)
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
                obj.person_year.person,
            )
            return None

        # Zero-padded CPR (as string)
        cpr = obj.identifier  # type: ignore[attr-defined]

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
            self.get_payment_amount(obj),  # type: ignore[arg-type]
            self.get_payment_date(obj),
            self.get_posting_date(obj),
            self.get_posting_text(obj),
            invoice_no,
            self.get_transaction_text(obj),
        )

        return self._get_prisme_batch_item_instance(
            prisme_batch,
            obj,
            transaction_pair,
            invoice_no,
        )

    def get_destination_folder(self, prisme_batch: PrismeBatch) -> str:
        prisme: dict = settings.PRISME  # type: ignore[misc]
        config_key = (
            "g68g69_export_folder"
            if prisme_batch.prefix < 32
            else "g68g69_export_mod11_folder"
        )
        return prisme[config_key]

    @transaction.atomic
    def upload_batch(
        self,
        prisme_batch: PrismeBatch,
        prisme_batch_items: list[PrismeBatchItem],
    ) -> PrismeBatch.Status:
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
            # Save all Prisme batch items belonging to the current batch
            PrismeBatchItem.objects.bulk_create(prisme_batch_items)
            # Run any post-processing on the Prisme batch items
            self.process_prisme_batch_items_on_successful_upload(prisme_batch_items)
        finally:
            prisme_batch.save()

        return prisme_batch.status

    def get_control_list_csv(self, encoding: str = "utf-8") -> BytesIO:
        with StringIO(newline="") as out:
            # Write each Prisme batch item to CSV report
            writer: DictWriter = DictWriter(
                out,
                fieldnames=["filnavn", "cpr", "beløb"],
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "filnavn": self.get_destination_filename(row.prisme_batch),
                        "cpr": row.cpr,
                        "beløb": format_number(
                            row.amount, decimal_sep=",", decimal_pos=2
                        ),
                    }
                    for row in self.get_control_list_data()
                ]
            )
            # Rewind `out` to start
            out.seek(0)
            # Convert `StringIO` to `BytesIO` so it can be uploaded using
            # `put_file_in_prisme_folder`.
            buf: BytesIO = BytesIO(out.getvalue().encode(encoding))
            return buf

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
        wait=retry_wait,  # settings.PRISME_RETRY_WAIT_SECONDS before retry
        after=after_log(logger, logging.WARNING),  # log all retry attempts
    )
    def _put_file_in_prisme_folder(
        self,
        buf: BytesIO | str,
        destination_folder: str,
        filename: str,
    ):
        put_file_in_prisme_folder(
            settings.PRISME,  # type: ignore[misc]
            buf,
            destination_folder,
            filename,
        )

    def export_batches(self, stdout: OutputWrapper, verbosity: int):
        queryset: QuerySet = self.get_queryset()

        num_objects: int = queryset.count()
        num_succeeded_batches: int = 0
        num_failed_batches: int = 0

        self.print_start_banner(stdout, num_objects)

        prisme_batch: PrismeBatch
        objs: QuerySet
        for prisme_batch, objs in self.get_batches(queryset):
            # Instantiate a new writer for each Prisme batch, ensuring that the line
            # numbers start from 0, etc.
            writer: G68G69TransactionWriter = self.get_g68_g69_transaction_writer()

            # Ensure the current Prisme batch is saved (so it has a PK)
            prisme_batch.save()

            # Build all items for this batch
            prisme_batch_items: list[PrismeBatchItem] = []
            for obj in objs:
                prisme_batch_item: PrismeBatchItem | None = self.get_prisme_batch_item(
                    prisme_batch,
                    obj,
                    writer,
                )
                if prisme_batch_item is not None:
                    prisme_batch_items.append(prisme_batch_item)
                    if verbosity >= 2:
                        stdout.write(f"{obj}")
                        stdout.write(prisme_batch_item.g68_content)
                        stdout.write(prisme_batch_item.g69_content)
                        stdout.write()
                else:
                    stdout.write(f"Could not build Prisme batch item for {obj}")

            # Export the current batch to Prisme
            status = self.upload_batch(prisme_batch, prisme_batch_items)

            # Collect/report upload status for this batch
            if status is PrismeBatch.Status.Sent:
                num_succeeded_batches += 1
                if verbosity >= 2:
                    stdout.write(f"Uploaded batch with pk={prisme_batch.pk}")
            if status is PrismeBatch.Status.Failed:
                num_failed_batches += 1
                if verbosity >= 2:
                    stdout.write(f"Failed to upload batch with pk={prisme_batch.pk}")

        if num_succeeded_batches > 0:
            self.print_success_banner(stdout, num_objects, num_succeeded_batches)

        if num_failed_batches > 0:
            self.print_failed_banner(stdout, num_failed_batches)
            return  # don't write control list if any batches failed to upload

        # Write control list CSV file to SFTP
        filename: str = self.get_control_list_filename()
        try:
            buf: BytesIO = self.get_control_list_csv()
            local_file: str = str(
                os.path.join(
                    settings.LOCAL_PRISME_CSV_STORAGE_FULL,  # type: ignore[misc]
                    filename,
                )
            )
            with open(local_file, "wb") as f:
                f.write(buf.getbuffer())
            self._put_file_in_prisme_folder(
                local_file,
                settings.PRISME["control_folder"],  # type: ignore[misc]
                filename,
            )
        except Exception:
            logger.exception("failed to upload control list %r", filename)
            stdout.write(f"FAILED to export control list '{filename}'.")
        else:
            self.print_control_list_success_banner(stdout)
            stdout.write("All done.")


class BatchExport(BaseExport):
    def __init__(self, year: int, month: int):
        self._year = year
        self._month = month

    def get_queryset(self) -> QuerySet:
        # Find all person months for this year/month which:
        # - have not yet been exported,
        # - have a full tax scope period overlapping the given month,
        # - and have a non-zero calculated benefit
        has_full_tax_scope_in_month: Exists = (
            TaxInformationPeriod.get_person_month_filter_annotation(
                self._year, self._month
            )
        )
        qs: QuerySet[PersonMonth] = (
            PersonMonth.objects.select_related("person_year__person", "prismebatchitem")
            .annotate(has_full_tax_scope_in_month=has_full_tax_scope_in_month)
            .filter(
                # This year and month
                person_year__year=self._year,
                month=self._month,
                # No previous export for this person, year and month
                prismebatchitem__isnull=True,
                # Only person months with a calculated benefit
                benefit_calculated__isnull=False,
                # Has full tax scope in this month
                has_full_tax_scope_in_month=True,
            )
            .exclude(benefit_calculated=Decimal("0"))
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

    def get_prisme_account_alias_lookup(
        self, obj: PersonMonth
    ) -> tuple[str | None, int]:
        location_code: str | None = obj.person_year.person.location_code
        tax_year: int = obj.person_year.year.year
        return location_code, tax_year

    def get_posting_text(self, obj: PersonMonth) -> str:
        cpr: str = obj.identifier  # type: ignore[attr-defined]
        date_formatted: str = obj.year_month.strftime("%b%y").upper()
        return f"SUILA-TAPIT-{cpr}-{date_formatted}"

    def get_transaction_text(self, obj: PersonMonth) -> str:
        # Note: this text is intentionally not marked for translation, as we do not
        # know the recipient user's preferred language.
        return "www.suila.gl takuuk"

    def get_payment_amount(self, obj: PersonMonth) -> Decimal | None:
        return obj.benefit_calculated

    def get_payment_date(self, obj: PersonMonth) -> date:
        # Payment date in Prisme is one day before the "official" payment date.
        # (The "official" payment date is the third Tuesday in the month two months
        # after the month we are exporting.)
        # Note, the payment date in Prisme not necessarily the same as the third Monday
        # in the month.
        return add_or_subtract_working_days(get_payment_date(obj.year, obj.month), -1)

    def get_posting_date(self, obj: PersonMonth) -> date:
        # Posting date is the second Tuesday two months after the given `PersonMonth`.
        # E.g. for a `PersonMonth` in February 2025, the posting date is April 8, 2025.
        return obj.year_month + relativedelta(months=2, weekday=TU(+2))

    def get_destination_filename(self, prisme_batch: PrismeBatch) -> str:
        return (
            "SUILA_G68_export_"
            f"{prisme_batch.prefix:02}_{self._year}_{self._month:02}.g68"
        )

    def process_prisme_batch_items_on_successful_upload(
        self, prisme_batch_items: list[PrismeBatchItem]
    ) -> None:
        person_months_to_update = []
        for prisme_batch_item in prisme_batch_items:
            person_month: PersonMonth = (
                prisme_batch_item.person_month  # type: ignore[assignment]
            )
            person_month.benefit_transferred = (
                prisme_batch_item.amount  # type: ignore[union-attr]
            )
            person_months_to_update.append(person_month)
        bulk_update_with_history(
            person_months_to_update, PersonMonth, ["benefit_transferred"]
        )

    def get_control_list_data(self) -> QuerySet:
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
            )
        )
        return prisme_batch_items

    def get_control_list_filename(self) -> str:
        return f"SUILA_kontrolliste_{self._year}_{self._month:02}.csv"

    def print_start_banner(self, stdout, num_objects: int) -> None:
        stdout.write(
            f"Found {num_objects} object(s) to export for year={self._year}, "
            f"month={self._month} ...",
        )

    def print_success_banner(
        self, stdout, num_objects: int, num_succeeded_batches: int
    ) -> None:
        stdout.write(
            f"Exported {num_succeeded_batches} batch(es) "
            f"({num_objects} object(s)) "
            f"for year={self._year}, month={self._month}."
        )

    def print_failed_banner(self, stdout, num_failed_batches: int):
        stdout.write(
            f"FAILED to export {num_failed_batches} batch(es) "
            f"for year={self._year}, month={self._month}."
        )

    def print_control_list_success_banner(self, stdout):
        pass  # can be implemented by subclass
        stdout.write(
            f"Exported control list for year={self._year}, month={self._month}."
        )

    def _get_prisme_batch_item_instance(
        self,
        prisme_batch: PrismeBatch,
        obj,
        transaction_pair,
        invoice_no,
    ) -> PrismeBatchItem:
        return PrismeBatchItem(
            prisme_batch=prisme_batch,
            person_month=obj,
            g68_content=transaction_pair.g68,
            g69_content=transaction_pair.g69,
            invoice_no=invoice_no,
            paused=obj.person_year.person.paused,
        )
