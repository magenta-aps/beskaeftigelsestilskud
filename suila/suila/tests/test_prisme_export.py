# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import os.path
import re
from csv import DictReader
from datetime import date, datetime
from decimal import Decimal
from io import TextIOWrapper
from unittest.mock import ANY, MagicMock, Mock, patch

from django.conf import settings
from django.core.management import call_command
from django.db.models import QuerySet
from django.test import TestCase
from django.test.utils import override_settings
from tenQ.client import ClientException
from tenQ.writer.g68 import (
    BetalingstekstLinje,
    Fakturanummer,
    G68Transaction,
    Udbetalingsdato,
)

from suila.integrations.prisme.benefits import BatchExport
from suila.models import (
    ManagementCommands,
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    TaxInformationPeriod,
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

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        file_path = os.path.join(
            settings.LOCAL_PRISME_CSV_STORAGE_FULL, "SUILA_kontrolliste_2025_01.csv"
        )
        if os.path.exists(file_path):
            os.remove(file_path)

    def test_get_person_month_queryset(self):
        """Given one or more `PersonMonth` objects, the method should return a queryset
        containing each `PersonMonth`, annotated with an `identifier` and `prefix`.
        """
        # Arrange
        cpr = 3112680000
        benefit_calculated = Decimal("1000")
        self._add_person_month(cpr, benefit_calculated)
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
                    benefit_calculated,
                )
            ],
            transform=lambda obj: (obj.identifier, obj.prefix, obj.benefit_calculated),
        )

    def test_get_person_year_queryset_excludes_person_months_without_benefit(self):
        """Given one or more `PersonMonth` objects, the method should skip objects that
        have a `benefit_calculated` which is 0 or None.
        """
        # Arrange: add two person months which should be skipped
        self._add_person_month(3112710000, benefit_calculated=None)
        self._add_person_month(3112720000, benefit_calculated=Decimal("0"))
        # Arrange: add one person month which should be included
        self._add_person_month(3112730000, benefit_calculated=Decimal("1000"))
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
        # Valid CPRs passing the modulus-11 test were generated using
        # https://janosh.neocities.org/javascript-personal-id-check-and-generator/
        self._add_person_month(101000028, Decimal("1000"))  # batch 01
        self._add_person_month(3101000000, Decimal("1000"))  # batch 31
        self._add_person_month(3101000078, Decimal("1000"))  # batch 31
        self._add_person_month(3101000001, Decimal("1000"))  # batch 32 (non-mod11)
        # Arrange
        export = self._get_instance()
        queryset = export.get_person_month_queryset()
        # Act
        batches: list[tuple[PrismeBatch, QuerySet[PersonMonth]]] = list(
            export.get_batches(queryset)
        )
        # Assert: we yield three batches: two for normal prefixes 01 and 31, and one for
        # the non-mod11 batch (prefix 32.)
        self.assertEqual(len(batches), 3)
        # Assert: first batch is for prefix 01 and contains one `PersonMonth` object
        batch_01_prisme_batch: PrismeBatch = batches[0][0]
        batch_01_person_months: QuerySet[PersonMonth] = batches[0][1]
        self.assertEqual(batch_01_prisme_batch.prefix, 1)
        self.assertQuerySetEqual(
            batch_01_person_months, queryset.filter(identifier="0101000028")
        )
        # Assert: second batch is for prefix 31 and contains two `PersonMonth` objects
        batch_31_prisme_batch: PrismeBatch = batches[1][0]
        batch_31_person_months: QuerySet[PersonMonth] = batches[1][1]
        self.assertEqual(batch_31_prisme_batch.prefix, 31)
        self.assertQuerySetEqual(
            batch_31_person_months,
            queryset.filter(identifier__in=("3101000000", "3101000078")),
        )
        # Assert: third batch is for prefix 32 and contains one `PersonMonth` object
        batch_32_prisme_batch: PrismeBatch = batches[2][0]
        batch_32_person_months: QuerySet[PersonMonth] = batches[2][1]
        self.assertEqual(batch_32_prisme_batch.prefix, 32)
        self.assertQuerySetEqual(
            batch_32_person_months, queryset.filter(identifier="3101000001")
        )

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

        # Assert basic attributes are present
        self.assertEqual(prisme_batch_item.prisme_batch, prisme_batch)
        self.assertEqual(prisme_batch_item.person_month, person_month)
        self.assertIsInstance(prisme_batch_item.g68_content, str)
        self.assertIsInstance(prisme_batch_item.g69_content, str)

        # Assert: the expected account alias is found in the G69 transaction
        account_alias = self._get_floating_field(prisme_batch_item.g69_content, 111)
        self.assertEqual(
            account_alias,
            # Finanslov, art, kommunekode, skatteår
            "240614" + "242040195" + "10400" + "25",
        )

        # Assert: G69 contains CPR in `Ydelsesmodtager` (field 133) and specifies CPR
        # (02) in `YdelsesmodtagerNrkode` (field 132)
        ydelsesmodtager_nrkode = self._get_floating_field(
            prisme_batch_item.g69_content, 132
        )
        ydelsesmodtager = self._get_floating_field(prisme_batch_item.g69_content, 133)
        self.assertEqual(ydelsesmodtager_nrkode, "02")
        self.assertEqual(ydelsesmodtager, "3112700000")

        # Assert: the field `Posteringstekst` is present and its value follows the
        # expected format.
        posting_text = self._get_floating_field(prisme_batch_item.g69_content, 153)
        self.assertEqual(posting_text, "SUILA-TAPIT-3112700000-JAN25")

        # Assert: the field `BetalingstekstLinje` contains the expected text in
        # floating field 40 (which is the first `BetalingstekstLinje` field.)
        payment_text = self._get_floating_field(
            prisme_batch_item.g68_content,
            BetalingstekstLinje._min_id,
            length=2,
        )
        self.assertEqual("www.suila.gl takuuk", payment_text)

        # Assert: the field `Fakturanummer` is present and its value follows the
        # expected format.
        # Format: Prisme batch ID (15 digits, zero padded), followed by line number
        # (5 digits, zero padded.)
        invoice_no = self._get_floating_field(
            prisme_batch_item.g68_content,
            Fakturanummer.id,
            length=2,
        )
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
        # Assert: an error is logged (but does not prevent the export from continuing)
        with self.assertLogs(level=logging.ERROR):
            # Act
            self._get_prisme_batch_item(export, prisme_batch)

    def test_get_prisme_batch_item_calculates_dates(self):
        """The G68 `Betalingsdato` field should be the third Monday of the month that
        is two months after the given `PersonMonth`.
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
        # Assert: the G68 `Udbetalingsdato` is third Monday of the month two months
        # after the `PersonMonth` to export.
        for field in G68Transaction.parse(prisme_batch_item.g68_content):
            if isinstance(field, Udbetalingsdato):
                self.assertEqual(field.val, date(2025, 3, 17))  # March 17, 2025
        # Assert: the G68 "posteringsdato" (field 110) is the second Tuesday of the
        # month two months after the `PersonMonth` to export.
        posteringsdato = self._get_floating_field(prisme_batch_item.g69_content, 110)
        self.assertEqual(posteringsdato, "20250311")  # March 11, 2025

    def test_get_payment_date(self):
        # Arrange
        february = self._add_person_month(311270000, Decimal("1000"), month=2)
        # Act
        export = self._get_instance()
        # Assert
        self.assertEqual(export.get_payment_date(february), date(2025, 4, 14))

    def test_get_posting_date(self):
        # Arrange
        february = self._add_person_month(311270000, Decimal("1000"), month=2)
        # Act
        export = self._get_instance()
        # Assert
        self.assertEqual(export.get_posting_date(february), date(2025, 4, 8))

    def test_upload_batch_handles_sftp_success(self):
        """Given a `PrismeBatch` object and a `PrismeBatchItem` queryset, the method
        should upload the serialized G68/G69 transaction pairs using the
        `put_file_in_prisme_folder` function. Upon calling the method, the `PrismeBatch`
        object should contain the correct upload status.
        """
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
        ) as mock_put:
            # Act
            export.upload_batch(prisme_batch, [prisme_batch_item])
            # Assert
            prisme_batch.refresh_from_db()
            # Assert: the upload function is called once (succeeding)
            mock_put.assert_called_once_with(
                settings.PRISME,
                ANY,  # `buf`
                ANY,  # `destination_folder`
                "SUILA_G68_export_"
                f"{prisme_batch.prefix:02}_{export._year}_"
                f"{export._month:02}"
                ".g68",
            )
            # Assert: the `PrismeBatch` object is updated
            self.assertEqual(prisme_batch.status, PrismeBatch.Status.Sent)
            self.assertEqual(prisme_batch.failed_message, "")
            # Assert: `PrismeBatchItem` objects exist for this batch
            self.assertGreater(
                PrismeBatchItem.objects.filter(prisme_batch=prisme_batch).count(),
                0,
            )

    def test_upload_batch_handles_sftp_failure(self):
        """Given a `PrismeBatch` object and a `PrismeBatchItem` queryset, the method
        should upload the serialized G68/G69 transaction pairs using the
        `put_file_in_prisme_folder` function. If `put_file_in_prisme_folder` raises an
        exception after retrying, `upload_batch` should record the failure on the
        `PrismeBatch` in question.
        """
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
            side_effect=ClientException("Uh-oh"),
        ) as mock_put:
            # Act
            export.upload_batch(prisme_batch, [prisme_batch_item])
            # Assert
            prisme_batch.refresh_from_db()
            # Assert: the upload function is called multiple times, until
            # giving up.
            mock_put.assert_called_with(
                settings.PRISME,
                ANY,  # `buf`
                ANY,  # `destination_folder`
                "SUILA_G68_export_"
                f"{prisme_batch.prefix:02}_{export._year}_"
                f"{export._month:02}"
                ".g68",
            )
            self.assertEqual(mock_put.call_count, 10)  # 10 retry attempts
            # Assert: the `PrismeBatch` object is updated
            self.assertEqual(prisme_batch.status, PrismeBatch.Status.Failed)
            self.assertEqual(prisme_batch.failed_message, "Uh-oh")
            # Assert: `PrismeBatchItem` objects do not exist for this batch
            self.assertEqual(
                PrismeBatchItem.objects.filter(prisme_batch=prisme_batch).count(),
                0,
            )

    def export_batches(self, stdout, verbosity=0, export=None, month=1, year=2025):
        if not export:
            export = self._get_instance(month=month, year=year)
        call_command(
            ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
            year=export._year,
            month=export._month,
            stdout=stdout,
            verbosity=verbosity,
            reraise=True,
        )

    def test_export_batches_verbosity_1(self):
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            self.export_batches(stdout, verbosity=1)

        self.assertEqual(stdout.write.call_count, 4)

    def test_export_batches_verbosity_2(self):
        # Arrange
        self._add_person_month(3112700000, Decimal("1000"))
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            self.export_batches(stdout, verbosity=2)

        self.assertEqual(stdout.write.call_count, 9)

    def test_export_batches_normal(self):
        """Given non-exported `PersonMonth` objects for this year and month, this method
        should export those `PersonMonth` objects as serialized G68/G69 transaction
        pairs in batches.
        """
        # Arrange
        # Valid CPR passing the modulus-11 test was generated using
        # https://janosh.neocities.org/javascript-personal-id-check-and-generator/
        person_month = self._add_person_month(3101000000, Decimal("1000"))
        self.assertEqual(person_month.benefit_transferred, 0)
        export = self._get_instance()
        stdout = Mock()
        with patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        ) as mock_put_file_in_prisme_folder:
            # Act
            self.export_batches(stdout, verbosity=2)
            # Assert
            self._assert_prisme_batch_items_state(
                export,
                mock_put_file_in_prisme_folder,
                stdout,
                # Single batch with prefix 31
                [31],
                # Single batch item with prefix 31
                [("3101000000", 31)],
                # Single file in "normal" folder
                [("g68g69", "SUILA_G68_export_31_2025_01.g68")],
            )
        person_month.refresh_from_db()
        self.assertGreater(person_month.benefit_transferred, 0)

    def test_export_batches_normal_and_non_mod11(self):
        # Arrange
        # Valid CPR passing the modulus-11 test was generated using
        # https://janosh.neocities.org/javascript-personal-id-check-and-generator/
        self._add_person_month(3101000000, Decimal("1000"))
        # Invalid CPR (valid CPR plus 1) - should go in its own batch and folder
        self._add_person_month(3101000001, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        ) as mock_put_file_in_prisme_folder:
            # Act
            self.export_batches(stdout, verbosity=2)
            # Assert
            self._assert_prisme_batch_items_state(
                export,
                mock_put_file_in_prisme_folder,
                stdout,
                # Two batches, prefixes 31 and 32
                [31, 32],
                # Two batch items, prefix 31 and 32
                [
                    ("3101000000", 31),  # valid CPR
                    ("3101000001", 32),  # non mod11 CPR
                ],
                # Two files, one in normal folder, and one in non-mod11 folder
                [
                    ("g68g69", "SUILA_G68_export_31_2025_01.g68"),
                    ("g68g69_mod11_cpr", "SUILA_G68_export_32_2025_01.g68"),
                ],
            )

    @override_settings(
        PRISME={
            "mod11_separate_cprs": ["3101000001"],
            **{k: v for k, v in settings.PRISME.items() if k != "mod11_separate_cprs"},
        },
    )
    def test_export_batches_handles_separate_non_mod11_cprs(self):
        # Arrange
        # Provide an invalid CPR that matches the CPR in `mod11_separate_cprs`
        self._add_person_month(3101000001, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        ) as mock_put_file_in_prisme_folder:
            # Act
            self.export_batches(stdout, verbosity=2)
            # Assert
            self._assert_prisme_batch_items_state(
                export,
                mock_put_file_in_prisme_folder,
                stdout,
                # One batch, whose "prefix" is identical to the CPR
                [3101000001],
                # One batch item
                [("3101000001", 3101000001)],
                # One file in the non-mod11 folder, using the CPR as prefix (instead of
                # 32.)
                [("g68g69_mod11_cpr", "SUILA_G68_export_3101000001_2025_01.g68")],
            )

    def test_export_batches_handles_none(self):
        """If `BatchExport.get_prisme_batch_item` returns None,
        `BatchExport.export_batches` should handle this case.
        """
        # Arrange: test person with location code that cannot be used to look up a valid
        # Prisme account alias
        person_month = self._add_person_month(
            3101000000, Decimal("1000"), municipality_code=0
        )
        stdout = Mock()
        with patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder"):
            # Act
            self.export_batches(stdout, verbosity=2)
            # Assert: no Prisme batch items were created
            self.assertQuerySetEqual(PrismeBatchItem.objects.all(), [])
            # Assert: message is written to output
            self.assertIn(
                f"Could not build Prisme batch item for {person_month}\n",
                [call.args[0] for call in stdout.write.call_args_list],
            )

    def test_export_batches_uploads_control_list(self):
        # Arrange
        self._add_person_month(3101000000, Decimal("1000"))
        export = self._get_instance()
        stdout = Mock()
        with patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        ) as mock_put:
            # Act
            self.export_batches(stdout, verbosity=2)

            # Assert: local file created
            folder = settings.LOCAL_PRISME_CSV_STORAGE_FULL
            expected_file = os.path.join(folder, "SUILA_kontrolliste_2025_01.csv")
            self.assertTrue(os.path.isfile(expected_file))

            # Assert: final call to `put_file_in_prisme_folder` is the CSV report
            last_call = mock_put.call_args_list[-1]
            self.assertEqual(last_call.args[3], "SUILA_kontrolliste_2025_01.csv")
            # Arrange: get CSV output
            output = export.get_control_list_csv()
            # Assert
            rows: list[dict] = list(DictReader(TextIOWrapper(output), delimiter=";"))
            self.assertListEqual(
                rows,
                [
                    {
                        "filnavn": "SUILA_G68_export_31_2025_01.g68",
                        "cpr": "3101000000",
                        "beløb": "1000,00",
                    }
                ],
            )

    @patch("suila.integrations.prisme.benefits.put_file_in_prisme_folder")
    def test_export_batches_handles_control_list_upload_failure(
        self, mock_put_file_in_prisme_folder: MagicMock
    ):
        # Arrange
        self._add_person_month(3101000000, Decimal("1000"))
        export = self._get_instance(month=11, year=2024)
        stdout = Mock()

        def fail_on_control_list_upload(buf, folder, filename):
            if "kontrolliste" in filename:
                raise ClientException("Failure in control list upload")

        mock_put_file_in_prisme_folder.side_effect = fail_on_control_list_upload

        self.export_batches(stdout, verbosity=2, export=export)
        self._assert_stdout_write_contains(stdout, "FAILED to export control list")

    def test_export_batches_reports_failure(self):
        for verbosity in (1, 2):
            # Arrange: add CPRs resulting in more than one batch being exported
            # (different prefixes.)
            self._add_person_month(3001000000, Decimal("1000"))
            self._add_person_month(3101000000, Decimal("1000"))
            stdout = Mock()
            with patch(
                "suila.integrations.prisme.benefits.put_file_in_prisme_folder",
                side_effect=ClientException("Uh-oh"),
            ):
                with self.subTest(verbosity=verbosity):
                    # Act
                    self.export_batches(stdout, verbosity=verbosity)
                    # Assert
                    self._assert_stdout_write_contains(
                        stdout, "FAILED to export 2 batch(es)"
                    )

    def _assert_stdout_write_contains(self, stdout, text: str):
        self.assertIn(
            text,
            "\n".join(
                call.args[0]
                for call in stdout.write.call_args_list
                if len(call.args) > 0
            ),
        )

    def _assert_prisme_batch_items_state(
        self,
        export: BatchExport,
        mock_put_file_in_prisme_folder,
        stdout,
        batch_prefixes: list[int],
        items: list[tuple[str, int]],
        file_paths: list[tuple[str, str]],
    ):
        # Assert: `PrismeBatch` object(s) exist with the expected status
        self.assertQuerySetEqual(
            PrismeBatch.objects.order_by("prefix").all(),
            [
                (batch_prefix, PrismeBatch.Status.Sent.value)
                for batch_prefix in batch_prefixes
            ],
            transform=lambda obj: (obj.prefix, obj.status),
        )
        # Assert: `PrismeBatchItem` object(s) exist for the expected prefixes and CPRs
        self.assertQuerySetEqual(
            PrismeBatchItem.objects.order_by("prisme_batch__prefix").all(),
            items,
            transform=lambda obj: (
                obj.person_month.person_year.person.cpr,
                obj.prisme_batch.prefix,
            ),
        )
        # Assert: the expected file(s) are uploaded to the expected folder(s)
        self.assertListEqual(
            [
                # Get folder name and filename from call arguments
                (call.args[2], call.args[3])
                for call in mock_put_file_in_prisme_folder.call_args_list
            ],
            file_paths + [("kontrolliste", "SUILA_kontrolliste_2025_01.csv")],
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
        benefit_calculated: Decimal | None,
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
        TaxInformationPeriod.objects.get_or_create(
            person_year=person_year,
            tax_scope="FULL",
            # Period covers entire year under test, to verify the previous behavior
            # (reading `PersonYear.tax_scope`) is preserved.
            start_date=datetime(year.year, 1, 1),
            end_date=datetime(year.year, 12, 31),
        )
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=person_year,
            month=month,
            benefit_calculated=benefit_calculated,
            import_date=date.today(),
        )
        return person_month

    def _get_floating_field(self, transaction: str, field: int, length: int = 3) -> str:
        field: str = str(field).zfill(length)
        match: re.Match = re.match(rf".*&{field}(?P<val>[^&]+)(&.*|$)", transaction)
        self.assertIsNotNone(match)
        return match.groupdict()["val"]
