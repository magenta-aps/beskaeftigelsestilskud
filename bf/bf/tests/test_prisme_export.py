# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from unittest.mock import ANY, Mock, patch

from django.conf import settings
from django.db.models import QuerySet
from django.test import TestCase
from tenQ.client import ClientException

from bf.integrations.prisme.benefits import BatchExport
from bf.models import (
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    Year,
)


class TestBatchExport(TestCase):
    def test_init(self):
        export = self._get_instance()
        self.assertEqual(export._year, 2024)
        self.assertEqual(export._month, 1)
        self.assertEqual(export._prisme_settings, settings.PRISME)

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
        self.assertQuerysetEqual(
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
        self.assertQuerysetEqual(batch_01_person_months, queryset.filter(prefix="01"))
        # Assert: second batch is for prefix 31 and contains two `PersonMonth` objects
        batch_31_prisme_batch: PrismeBatch = batches[1][0]
        batch_31_person_months: QuerySet[PersonMonth] = batches[1][1]
        self.assertEqual(batch_31_prisme_batch.prefix, 31)
        self.assertQuerysetEqual(batch_31_person_months, queryset.filter(prefix="31"))

    def test_get_prisme_batch_item(self):
        """Given a `PrismeBatch` object, a `PersonMonth object, and a
        `G68G69TransactionWriter` instance, the method should return a suitable
        `PrismeBatchItem`.
        """
        # Arrange
        self._add_person_month(311270000, Decimal("1000"))
        prisme_batch = PrismeBatch()
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

    def test_upload_batch(self):
        """Given a `PrismeBatch` object and a `PrismeBatchItem` queryset, the method
        should upload the serialized G68/G69 transaction pairs using the
        `put_file_in_prisme_folder` function. Upon calling the method, the `PrismeBatch`
        object should contain the correct upload status.
        """
        for test_upload_exception in (False, True):
            with self.subTest(test_upload_exception=test_upload_exception):
                # Arrange
                self._add_person_month(311270000, Decimal("1000"))
                prisme_batch, _ = PrismeBatch.objects.get_or_create(
                    prefix=31, export_date=date.today()
                )
                export = self._get_instance()
                prisme_batch_item, person_month = self._get_prisme_batch_item(
                    export, prisme_batch
                )
                with patch(
                    "bf.integrations.prisme.benefits.put_file_in_prisme_folder",
                    side_effect=(
                        ClientException("Uh-oh") if test_upload_exception else None
                    ),
                ) as mock_put:
                    # Act
                    export.upload_batch(prisme_batch, [prisme_batch_item])
                    # Assert: the upload function is called
                    mock_put.assert_called_once_with(settings.PRISME, ANY, ANY, ANY)
                    # Assert: the `PrismeBatch` object is updated
                    prisme_batch.refresh_from_db()
                    if test_upload_exception:
                        self.assertEqual(prisme_batch.status, PrismeBatch.Status.Failed)
                        self.assertEqual(prisme_batch.failed_message, "Uh-oh")
                    else:
                        self.assertEqual(prisme_batch.status, PrismeBatch.Status.Sent)
                        self.assertEqual(prisme_batch.failed_message, "")

    def test_export_batches(self):
        """Given non-exported `PersonMonth` objects for this year and month, this method
        should export those `PersonMonth` objects as serialized G68/G69 transaction
        pairs in batches.
        """
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch("bf.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            export.export_batches(stdout)
            # Assert: `PrismeBatch` object(s) exist with the expected status
            self.assertQuerysetEqual(
                PrismeBatch.objects.all(),
                [(31, PrismeBatch.Status.Sent.value)],
                transform=lambda obj: (obj.prefix, obj.status),
            )
            # Assert: `PrismeBatchItem` object(s) exist
            self.assertQuerysetEqual(
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
            self.assertQuerysetEqual(
                export.get_person_month_queryset(),
                PersonMonth.objects.none(),
            )
            # Assert: CLI output is written to `stdout`
            stdout.write.assert_called()

    def _get_instance(self, year: int = 2024, month: int = 1) -> BatchExport:
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
        benefit_paid: Decimal,
        year: int = 2024,
        month: int = 1,
    ) -> PersonMonth:
        year, _ = Year.objects.get_or_create(year=year)
        person, _ = Person.objects.get_or_create(cpr=cpr)
        person_year, _ = PersonYear.objects.get_or_create(year=year, person=person)
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=person_year,
            month=month,
            benefit_paid=benefit_paid,
            import_date=date.today(),
        )
        return person_month