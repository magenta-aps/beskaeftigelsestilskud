# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import re
from datetime import date
from decimal import Decimal
from unittest.mock import ANY, Mock, patch

from django.conf import settings
from django.core.management import call_command
from django.db.models import QuerySet
from django.test import TestCase
from tenQ.client import ClientException
from tenQ.writer.g68 import BetalingstekstLinje, Fakturanummer

from suila.integrations.prisme.benefits import BatchExport, MissingAccountAliasException
from suila.models import (
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    Year,
)


class TestBatchExport(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command(
            "load_prisme_account_aliases",
        )

    def test_init(self):
        export = self._get_instance()
        self.assertEqual(export._year, 2025)
        self.assertEqual(export._month, 1)

    def test_get_person_month_queryset(self):
        """Given one or more `PersonMonth` objects, the method should return a queryset
        containing each `PersonMonth`, annotated with an `identifier` and `prefix`.
        """
        # Arrange
        cpr = 3112680000
        benefit_paid = Decimal("1000")
        self._add_person_month(cpr, benefit_paid)
        export = self._get_instance()
        # Act
        queryset = export.get_person_month_queryset()
        # Assert
        self.assertQuerySetEqual(
            queryset,
            [
                (
                    str(cpr),  # "identifier": CPR as string
                    str(cpr)[:2],  # "prefix": first two digits of CPR (as string)
                    benefit_paid,
                )
            ],
            transform=lambda obj: (obj.identifier, obj.prefix, obj.benefit_paid),
        )

    def test_get_person_year_queryset_excludes_person_months_without_benefit(self):
        """Given one or more `PersonMonth` objects, the method should skip objects that
        have a `benefit_paid` which is 0 or None.
        """
        # Arrange: add two person months which should be skipped
        self._add_person_month(3112710000, benefit_paid=None)
        self._add_person_month(3112720000, benefit_paid=Decimal("0"))
        # Arrange: add one person month which should be included
        self._add_person_month(3112730000, benefit_paid=Decimal("1000"))
        # Arrange
        export = self._get_instance()
        # Act
        queryset = export.get_person_month_queryset()
        # Assert
        self.assertEqual(queryset.count(), 1)

    def test_get_batches(self):
        """Given a `PersonMonth` queryset from the `get_person_month_queryset` method,
        the method should return a generator that yields one `PrismeBatch` and its
        matching `PersonMonth` objects for each unique `prefix`.
        """
        # Arrange: ensure that we see more than one batch, and that the second batch has
        # more than one `PersonMonth`.
        self._add_person_month(101700000, Decimal("1000"))  # batch 01
        self._add_person_month(3112700000, Decimal("1000"))  # batch 31
        self._add_person_month(3112710000, Decimal("1000"))  # batch 31
        # Arrange
        export = self._get_instance()
        queryset = export.get_person_month_queryset()
        # Act
        batches: list[tuple[PrismeBatch, QuerySet[PersonMonth]]] = list(
            export.get_batches(queryset)
        )
        # Assert: we yield two batches: for prefix 01 and 31, respectively
        self.assertEqual(len(batches), 2)
        # Assert: first batch is for prefix 01 and contains one `PersonMonth` object
        batch_01_prisme_batch: PrismeBatch = batches[0][0]
        batch_01_person_months: QuerySet[PersonMonth] = batches[0][1]
        self.assertEqual(batch_01_prisme_batch.prefix, 1)
        self.assertQuerySetEqual(batch_01_person_months, queryset.filter(prefix="01"))
        # Assert: second batch is for prefix 31 and contains two `PersonMonth` objects
        batch_31_prisme_batch: PrismeBatch = batches[1][0]
        batch_31_person_months: QuerySet[PersonMonth] = batches[1][1]
        self.assertEqual(batch_31_prisme_batch.prefix, 31)
        self.assertQuerySetEqual(batch_31_person_months, queryset.filter(prefix="31"))

    def test_get_prisme_batch_item(self):
        """Given a `PrismeBatch` object, a `PersonMonth object, and a
        `G68G69TransactionWriter` instance, the method should return a suitable
        `PrismeBatchItem`.
        """
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        prisme_batch, _ = PrismeBatch.objects.get_or_create(
            prefix=0, export_date=date(2025, 1, 1)
        )
        export = self._get_instance()
        # Act
        prisme_batch_item, person_month = self._get_prisme_batch_item(
            export, prisme_batch
        )
        # Assert
        self.assertEqual(prisme_batch_item.prisme_batch, prisme_batch)
        self.assertEqual(prisme_batch_item.person_month, person_month)
        self.assertIsInstance(prisme_batch_item.g68_content, str)
        self.assertIsInstance(prisme_batch_item.g69_content, str)
        # Assert: the complete account alias (including CPR) is found in the G69
        # transaction.
        account_alias = self._get_floating_field(prisme_batch_item.g69_content, 111)
        self.assertEqual(
            account_alias,
            # Root, tax municipality code, and tax year
            "100045240614101010000242040195" + "10400" + "25",
        )
        # Assert: G69 contains CPR in `Ydelsesmodtager` (field 133) and specifies CPR
        # (02) in `YdelsesmodtagerNrkode` (field 132)
        ydelsesmodtager_nrkode = self._get_floating_field(
            prisme_batch_item.g69_content, 132
        )
        ydelsesmodtager = self._get_floating_field(prisme_batch_item.g69_content, 133)
        self.assertEqual(ydelsesmodtager_nrkode, "02")
        self.assertEqual(ydelsesmodtager, "3112700000")
        # Assert: the field `BetalingstekstLinje` follows the expected format
        text = self._get_floating_field(
            prisme_batch_item.g68_content,
            BetalingstekstLinje._min_id,
            length=2,
        )
        self.assertEqual(text, "SUILA" + "3112700000" + "JAN25")
        self.assertLessEqual(len(text), 20)
        # Assert: the field `Fakturanummer` is present and its value follows the
        # expected format.
        invoice_no = self._get_floating_field(
            prisme_batch_item.g68_content,
            Fakturanummer.id,
            length=2,
        )
        # Format: Prisme batch ID (15 digits, zero padded), followed by line number
        # (5 digits, zero padded.)
        self.assertRegex(invoice_no, f"{prisme_batch.pk:015d}\\d{{5}}")
        self.assertEqual(invoice_no, prisme_batch_item.invoice_no)

    def test_get_prisme_batch_item_exception_on_missing_location_code(self):
        """If a `Person` has no `location_code`, the corresponding `PrismeAccountAlias`
        cannot be retrieved, and `get_prisme_batch_item` should raise an exception.
        """
        # Arrange
        self._add_person_month(
            3112700000,
            Decimal("1000"),
            municipality_code=None,  # type: ignore
        )
        prisme_batch, _ = PrismeBatch.objects.get_or_create(
            prefix=0, export_date=date(2025, 1, 1)
        )
        export = self._get_instance()
        with self.assertRaises(MissingAccountAliasException):
            # Act
            self._get_prisme_batch_item(export, prisme_batch)

    def test_upload_batch(self):
        """Given a `PrismeBatch` object and a `PrismeBatchItem` queryset, the method
        should upload the serialized G68/G69 transaction pairs using the
        `put_file_in_prisme_folder` function. Upon calling the method, the `PrismeBatch`
        object should contain the correct upload status.
        """
        for test_upload_exception in (False, True):
            with self.subTest(test_upload_exception=test_upload_exception):
                # Arrange
                self._add_person_month(3112700000, Decimal("1000"))
                prisme_batch, _ = PrismeBatch.objects.get_or_create(
                    prefix=31, export_date=date.today()
                )
                export = self._get_instance()
                prisme_batch_item, person_month = self._get_prisme_batch_item(
                    export, prisme_batch
                )
                with patch(
                    "suila.integrations.prisme.benefits.put_file_in_prisme_folder",
                    side_effect=(
                        ClientException("Uh-oh") if test_upload_exception else None
                    ),
                ) as mock_put:
                    # Act
                    export.upload_batch(prisme_batch, [prisme_batch_item])
                    # Assert: the upload function is called
                    mock_put.assert_called_once_with(
                        settings.PRISME,
                        ANY,  # `buf`
                        ANY,  # `destination_folder`
                        "RES_G68_export_"
                        f"{prisme_batch.prefix:02}_{export._year}_{export._month:02}"
                        ".g68",
                    )
                    # Assert: the `PrismeBatch` object is updated
                    prisme_batch.refresh_from_db()
                    if test_upload_exception:
                        self.assertEqual(prisme_batch.status, PrismeBatch.Status.Failed)
                        self.assertEqual(prisme_batch.failed_message, "Uh-oh")
                    else:
                        self.assertEqual(prisme_batch.status, PrismeBatch.Status.Sent)
                        self.assertEqual(prisme_batch.failed_message, "")

    def test_export_batches_verbosity_1(self):
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            export.export_batches(stdout, verbosity=1)

        self.assertEqual(stdout.write.call_count, 2)

    def test_export_batches_verbosity_2(self):
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            export.export_batches(stdout, verbosity=2)

        self.assertEqual(stdout.write.call_count, 7)

    def test_export_batches(self):
        """Given non-exported `PersonMonth` objects for this year and month, this method
        should export those `PersonMonth` objects as serialized G68/G69 transaction
        pairs in batches.
        """
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            export.export_batches(stdout, verbosity=2)
            # Assert: `PrismeBatch` object(s) exist with the expected status
            self.assertQuerySetEqual(
                PrismeBatch.objects.all(),
                [(31, PrismeBatch.Status.Sent.value)],
                transform=lambda obj: (obj.prefix, obj.status),
            )
            # Assert: `PrismeBatchItem` object(s) exist
            self.assertQuerySetEqual(
                PrismeBatchItem.objects.all(),
                [("3112700000", 31)],
                transform=lambda obj: (
                    obj.person_month.person_year.person.cpr,
                    obj.prisme_batch.prefix,
                ),
            )
            # Assert: all `PersonMonth` objects are now exported (= have a corresponding
            # `PrismeBatchItem` object.) Thus, the batch export will not "see" them
            # again.
            self.assertQuerySetEqual(
                export.get_person_month_queryset(),
                PersonMonth.objects.none(),
            )
            # Assert: CLI output is written to `stdout`
            stdout.write.assert_called()

    def _get_instance(self, year: int = 2025, month: int = 1) -> BatchExport:
        return BatchExport(year, month)

    def _get_prisme_batch_item(
        self,
        export: BatchExport,
        prisme_batch: PrismeBatch,
    ) -> tuple[PrismeBatchItem, PersonMonth]:
        # Helper method to call `get_prisme_batch_item`
        person_month = export.get_person_month_queryset().first()
        writer = export.get_g68_g69_transaction_writer()
        prisme_batch_item = export.get_prisme_batch_item(
            prisme_batch,
            person_month,
            writer,
        )
        return prisme_batch_item, person_month

    def _add_person_month(
        self,
        cpr: int,
        benefit_paid: Decimal | None,
        year: int = 2025,
        month: int = 1,
        municipality_code: int = 956,
    ) -> PersonMonth:
        year, _ = Year.objects.get_or_create(year=year)
        person, _ = Person.objects.get_or_create(
            cpr=cpr,
            defaults={"location_code": municipality_code},
        )
        person_year, _ = PersonYear.objects.get_or_create(year=year, person=person)
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=person_year,
            month=month,
            benefit_paid=benefit_paid,
            import_date=date.today(),
        )
        return person_month

    def _get_floating_field(self, transaction: str, field: int, length: int = 3) -> str:
        field: str = str(field).zfill(length)
        match: re.Match = re.match(rf".*&{field}(?P<val>\w+)(&.*|$)", transaction)
        self.assertIsNotNone(match)
        return match.groupdict()["val"]
