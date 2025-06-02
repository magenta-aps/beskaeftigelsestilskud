# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import fields
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django.test.utils import override_settings

from suila.integrations.prisme.posting_status import PostingStatus, PostingStatusImport
from suila.management.commands.load_prisme_benefits_posting_status import (
    Command as LoadPrismeBenefitsPostingStatusCommand,
)
from suila.models import (
    PersonMonth,
    PrismeBatch,
    PrismeBatchItem,
    PrismePostingStatusFile,
)
from suila.tests.helpers import ImportTestCase

_EXAMPLE_1 = "§15;3112700000;00587075;9700;2025/03/09;RJ00;JKH Tesst;§15-000000059;"
_EXAMPLE_2 = "§15;3112700000;01587075;9700;2025/03/09;RJ00;JKH Tesst;§15-000000059;"
_EXAMPLE_3 = "§15;3112700000;02587075;1313;2020/03/09;RJ00;JKH Tesst;§15-000000059;"


class TestLoadPrismeBenefitsPostingStatusCommand(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.command = LoadPrismeBenefitsPostingStatusCommand()

    def test_command_calls_import(self):
        with patch(
            "suila.management.commands.load_prisme_benefits_posting_status."
            "PostingStatusImport",
        ) as mock_import:
            call_command(self.command)
            mock_import.assert_called_once()


class TestPostingStatus(SimpleTestCase):
    def test_from_csv_row(self):
        obj = PostingStatus.from_csv_row(_EXAMPLE_1.split(";"))
        self.assertEqual(obj.type, "§15")
        self.assertEqual(obj.cpr, 311270_0000)
        self.assertEqual(obj.invoice_no, "00587075")
        self.assertEqual(obj.amount, 9700)
        self.assertEqual(obj.due_date, date(2025, 3, 9))
        self.assertEqual(obj.error_code, "RJ00")
        self.assertEqual(obj.error_description, "JKH Tesst")
        self.assertEqual(obj.voucher_no, "§15-000000059")


class PostingStatusImportTestCase(ImportTestCase):
    @classmethod
    def _add_prisme_batch_item(
        cls,
        person_month: PersonMonth,
        invoice_no: str,
        posting_status_filename: str = "",
    ) -> PrismeBatchItem:
        prisme_batch, _ = PrismeBatch.objects.get_or_create(
            status=PrismeBatch.Status.Sent,
            prefix=0,
            export_date=date(2020, 1, 1),
        )
        if posting_status_filename:
            posting_status_file, _ = PrismePostingStatusFile.objects.get_or_create(
                filename=posting_status_filename
            )
        else:
            posting_status_file = None
        prisme_batch_item, _ = PrismeBatchItem.objects.get_or_create(
            prisme_batch=prisme_batch,
            person_month=person_month,
            invoice_no=invoice_no,
            posting_status_file=posting_status_file,
        )
        return prisme_batch_item


class TestPostingStatusImport(PostingStatusImportTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # This item has an invoice number matching the invoice number in the mocked
        # "posting status" CSV file, and should be considered "failed to post."
        cls._item_on_posting_status_list = cls._add_prisme_batch_item(
            cls.add_person_month(311270_0000),
            "00587075",
        )
        # This item has an invoice number which is not present in the mocked "posting
        # status" CSV file, and should be considered "succeeded to post."
        cls._item_not_on_posting_status_list = cls._add_prisme_batch_item(
            cls.add_person_month(311271_0000),
            "12345678",
        )

    @override_settings(PRISME={"machine_id": 1234})
    def test_valid_filenames_are_processed(self):
        # Arrange
        instance = PostingStatusImport()
        filename = "§38_01234_11-03-2025_000000.csv"
        # Act
        filenames = instance._process_filenames({filename})
        # Assert
        self.assertListEqual([filename], filenames)

    @override_settings(PRISME={"machine_id": 1234})
    def test_invalid_filenames_are_skipped(self):
        # Arrange
        instance = PostingStatusImport()
        filename = "invalid_name.csv"
        # Act
        filenames = instance._process_filenames({filename})
        # Assert
        self.assertListEqual([], filenames)

    @override_settings(PRISME={"machine_id": 1234})
    def test_valid_filenames_are_sorted_by_date(self):
        # Arrange
        instance = PostingStatusImport()
        valid_filenames = {
            # Filenames are in reverse order
            "§38_01234_11-03-2025_000001.csv",
            "§38_01234_11-03-2025_000000.csv",
        }
        # Act
        filenames = instance._process_filenames(valid_filenames)
        # Assert: filenames are sorted chronologically
        self.assertListEqual(
            [
                "§38_01234_11-03-2025_000000.csv",
                "§38_01234_11-03-2025_000001.csv",
            ],
            filenames,
        )

    def test_get_max_date_from_csv(self):
        # Arrange
        instance = PostingStatusImport()
        defaults = {f.name: None for f in fields(PostingStatus) if f.name != "due_date"}
        rows = [
            PostingStatus(due_date=date(2020, 1, 15), **defaults),
            PostingStatus(due_date=date(2019, 12, 15), **defaults),
        ]
        # Act
        max_date = instance._get_max_date(rows)
        # Assert: the "max date" is the latest date in `rows`, minus two months, and its
        # day is always 1.
        self.assertEqual(max_date, date(2019, 11, 1))

    def test_queryset_is_filtered_by_max_date(self):
        # Arrange
        instance = PostingStatusImport()
        # Arrange: get queryset of two Prisme batch items in January 2020
        all_pks = [
            self._item_on_posting_status_list.pk,
            self._item_not_on_posting_status_list.pk,
        ]
        qs = PrismeBatchItem.objects.filter(pk__in=all_pks)
        # Arrange: test two dates
        for max_date, expected_pks in (
            (date(2020, 1, 1), all_pks),
            (date(2019, 12, 1), []),
        ):
            with self.subTest("Queryset is filtered by max date", max_date=max_date):
                # Act
                result = instance._filter_prisme_batch_items_on_date(qs, max_date)
                # Assert
                self.assertQuerySetEqual(
                    expected_pks, result.values_list("pk", flat=True)
                )

    @override_settings(PRISME={"machine_id": 1234, "posting_status_folder": "foo"})
    def test_import_posting_status_marks_failure(self):
        # Arrange
        instance = PostingStatusImport()
        # Act: import a single posting status file
        with self.mock_sftp_server_folder(
            ("§38_01234_11-03-2025_000000.csv", _EXAMPLE_1),
        ):
            instance.import_posting_status(MagicMock(), 1)
        # Assert: the matching Prisme batch item is marked as failed
        self._item_on_posting_status_list.refresh_from_db()
        self.assertEqual(
            self._item_on_posting_status_list.posting_status_file.filename,
            "§38_01234_11-03-2025_000000.csv",
        )
        self.assertEqual(
            self._item_on_posting_status_list.status,
            PrismeBatchItem.PostingStatus.Failed,
        )
        self.assertEqual(self._item_on_posting_status_list.error_code, "RJ00")
        self.assertEqual(
            self._item_on_posting_status_list.error_description, "JKH Tesst"
        )

    @override_settings(PRISME={"machine_id": 1234, "posting_status_folder": "foo"})
    def test_import_posting_status_updates_prev_failure_to_posted(self):
        # Arrange
        instance = PostingStatusImport()
        # Act: import two posting status files:
        # - first file marks the item as failed
        # - second file marks the same item as posted (as it is no longer present in the
        # file.)
        with self.mock_sftp_server_folder(
            ("§38_01234_11-03-2025_000000.csv", _EXAMPLE_1),  # first file
            ("§38_01234_11-03-2025_000001.csv", _EXAMPLE_2),  # second file
        ):
            instance.import_posting_status(MagicMock(), 1)
        # Assert: the matching Prisme batch item is marked as posted
        self._item_on_posting_status_list.refresh_from_db()
        self.assertEqual(
            self._item_on_posting_status_list.posting_status_file.filename,
            "§38_01234_11-03-2025_000001.csv",
        )
        self.assertEqual(
            self._item_on_posting_status_list.status,
            PrismeBatchItem.PostingStatus.Posted,
        )
        self.assertEqual(self._item_on_posting_status_list.error_code, "")
        self.assertEqual(self._item_on_posting_status_list.error_description, "")

    @override_settings(PRISME={"machine_id": 1234, "posting_status_folder": "foo"})
    def test_import_posting_status_stdout(self):
        # Arrange
        stdout = MagicMock()
        instance = PostingStatusImport()
        with self.mock_sftp_server_folder(
            ("§38_01234_11-03-2025_000000.csv", _EXAMPLE_1),
        ):
            # Act
            instance.import_posting_status(stdout, 2)
        # Assert
        self.assertListEqual(
            [call.args[0] for call in stdout.write.call_args_list],
            [
                "Loading new file: §38_01234_11-03-2025_000000.csv",
                "Processing 2 Prisme batch items (max date = 2025-01-01) ...",
                "Updated 1 to status=failed",
                "Updated 1 to status=posted",
                "\n",
            ],
        )

    @override_settings(PRISME={"posting_status_folder": "foo"})
    def test_get_remote_folder_name(self):
        # Arrange
        instance = PostingStatusImport()
        # Act and assert
        self.assertEqual(instance.get_remote_folder_name(), "foo")

    def test_parse(self):
        # Arrange
        instance = PostingStatusImport()
        with self.mock_sftp_server(_EXAMPLE_1):
            # Act
            result: list[PostingStatus] = instance._parse("filename1.csv")
            # Assert
            self.assertIsInstance(result, list)
            self.assertIsInstance(result[0], PostingStatus)


class TestPostingStatusImportMissingInvoiceNumber(PostingStatusImportTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # This item matches the data in the mocked "posting status" CSV file on CPR,
        # date and amount (but not on invoice number.) It should cause the import to
        # mark the Prisme batch item as failed.
        cls._matching_item = cls._add_prisme_batch_item(
            cls.add_person_month(311270_0000, benefit_transferred=Decimal("1313.00")),
            "01",
        )
        # This item does not match the data in the mocked "posting status" CSV file on
        # neither CPR, date and amount, nor on invoice number. It should be skipped by
        # the import.
        cls._non_matching_item = cls._add_prisme_batch_item(
            cls.add_person_month(311270_0001, benefit_transferred=Decimal("1313.00")),
            "02",
        )

    @override_settings(PRISME={"machine_id": 1234, "posting_status_folder": "foo"})
    def test_import_posting_status_by_cpr_date_and_amount(self):
        # Arrange
        instance = PostingStatusImport()
        # In this test, `_EXAMPLE_1` does not match any Prisme batch item (neither on
        # invoice number, nor CPR/date/amount) while `_EXAMPLE_3` matches on CPR/date/
        # amount, but not on invoice number.
        with self.mock_sftp_server_folder(
            ("§38_01234_11-03-2025_000000.csv", _EXAMPLE_1),
            ("§38_01234_11-03-2025_000001.csv", _EXAMPLE_3),
        ):
            # Act
            instance.import_posting_status(MagicMock(), 1)
        # Assert: matching item is marked as failed
        self._matching_item.refresh_from_db()
        self.assertEqual(
            self._matching_item.status, PrismeBatchItem.PostingStatus.Failed
        )
        self.assertNotEqual(self._matching_item.posting_status_file.filename, "")
        self.assertEqual(self._matching_item.error_code, "RJ00")
        self.assertEqual(self._matching_item.error_description, "JKH Tesst")
        # Assert: non-matching item is marked as posted
        self._non_matching_item.refresh_from_db()
        self.assertEqual(
            self._non_matching_item.status, PrismeBatchItem.PostingStatus.Posted
        )
        self.assertIsNotNone(self._non_matching_item.posting_status_file)
        self.assertEqual(self._non_matching_item.error_code, "")
        self.assertEqual(self._non_matching_item.error_description, "")
