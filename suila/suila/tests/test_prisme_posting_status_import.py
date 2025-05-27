# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django.test.utils import override_settings

from suila.integrations.prisme.posting_status import (
    PostingStatus,
    PostingStatusImport,
    PostingStatusImportMissingInvoiceNumber,
)
from suila.management.commands.load_prisme_benefits_posting_status import (
    Command as LoadPrismeBenefitsPostingStatusCommand,
)
from suila.models import PersonMonth, PrismeBatch, PrismeBatchItem
from suila.tests.helpers import ImportTestCase

_EXAMPLE_1 = "§15;3112700000;00587075;9700;2021/04/09;RJ00;JKH Tesst;§15-000000059;"
_EXAMPLE_2 = "§15;3112700000;01587075;9700;2021/04/09;RJ00;JKH Tesst;§15-000000059;"
_EXAMPLE_3 = "§15;3112700000;02587075;1313;2020/03/17;RJ00;JKH Tesst;§15-000000059;"


class TestLoadPrismeBenefitsPostingStatusCommand(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.command = LoadPrismeBenefitsPostingStatusCommand()

    def test_command_defaults(self):
        """The default behavior is to use `PostingStatusImport`"""
        with patch(
            "suila.management.commands.load_prisme_benefits_posting_status."
            "PostingStatusImport",
        ) as mock_import:
            call_command(self.command)
            mock_import.assert_called_once()

    def test_command_handles_unknown_invoice_number_arg(self):
        """`--unknown-invoice-number` uses `PostingStatusImportMissingInvoiceNumber`"""
        with patch(
            "suila.management.commands.load_prisme_benefits_posting_status."
            "PostingStatusImportMissingInvoiceNumber",
        ) as mock_import:
            call_command(self.command, unknown_invoice_number=True)
            mock_import.assert_called_once()


class TestPostingStatus(SimpleTestCase):
    def test_from_csv_row(self):
        obj = PostingStatus.from_csv_row(_EXAMPLE_1.split(";"))
        self.assertEqual(obj.type, "§15")
        self.assertEqual(obj.cpr, 311270_0000)
        self.assertEqual(obj.invoice_no, "00587075")
        self.assertEqual(obj.amount, 9700)
        self.assertEqual(obj.due_date, date(2021, 4, 9))
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
        prisme_batch_item, _ = PrismeBatchItem.objects.get_or_create(
            prisme_batch=prisme_batch,
            person_month=person_month,
            invoice_no=invoice_no,
            posting_status_filename=posting_status_filename,
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

    def test_import_posting_status_is_idempotent(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)

        # First run
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2):
            instance.import_posting_status(MagicMock(), 1)
        # First run creates the expected item statuses
        self._assert_expected_item_statuses()

        # Second run
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2):
            instance.import_posting_status(MagicMock(), 1)
        # Second run: result is identical to first run
        self._assert_expected_item_statuses()

    def test_import_posting_status_verbosity_2(self):
        # Arrange
        stdout = MagicMock()
        instance = PostingStatusImport(2020, 1)
        with self.mock_sftp_server(_EXAMPLE_1):
            # Act
            instance.import_posting_status(stdout, 2)
        # Assert
        self.assertEqual(stdout.write.call_count, 4)

    @override_settings(PRISME={"posting_status_folder": "foo"})
    def test_get_remote_folder_name(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)
        # Act and assert
        self.assertEqual(instance.get_remote_folder_name(), "foo")

    def test_parse(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)
        with self.mock_sftp_server(_EXAMPLE_1):
            # Act
            result: list[PostingStatus] = instance._parse("filename1.csv")
            # Assert
            self.assertIsInstance(result, list)
            self.assertIsInstance(result[0], PostingStatus)

    def _assert_expected_item_statuses(self):
        self.assertQuerySetEqual(
            PrismeBatchItem.objects.all()
            .order_by("invoice_no")
            .values("invoice_no", "status"),
            [
                # This invoice number is present in `_EXAMPLE_1` and should thus be
                # marked as failed.
                {
                    "invoice_no": "00587075",
                    "status": PrismeBatchItem.PostingStatus.Failed.value,
                },
                # This invoice number is neither present in `_EXAMPLE_1` nor
                # `_EXAMPLE_2`, and thus should be marked as succeeded.
                {
                    "invoice_no": "12345678",
                    "status": PrismeBatchItem.PostingStatus.Posted.value,
                },
            ],
        )


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

    def test_import_posting_status_by_cpr_date_and_amount(self):
        # Arrange
        instance = PostingStatusImportMissingInvoiceNumber()
        # In this test, `_EXAMPLE_1` does not match any Prisme batch item (neither on
        # invoice number, nor CPR/date/amount) while `_EXAMPLE_3` matches on CPR/date/
        # amount, but not on invoice number.
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_3):
            # Act
            instance.import_posting_status(MagicMock(), 1)
        # Assert: matching item is marked as failed
        self._matching_item.refresh_from_db()
        self.assertEqual(
            self._matching_item.status, PrismeBatchItem.PostingStatus.Failed
        )
        self.assertNotEqual(self._matching_item.posting_status_filename, "")
        self.assertEqual(self._matching_item.error_code, "RJ00")
        self.assertEqual(self._matching_item.error_description, "JKH Tesst")
        # Assert: non-matching item is unchanged
        self._non_matching_item.refresh_from_db()
        self.assertEqual(
            self._non_matching_item.status, PrismeBatchItem.PostingStatus.Sent
        )
        self.assertEqual(self._non_matching_item.posting_status_filename, "")
        self.assertEqual(self._non_matching_item.error_code, "")
        self.assertEqual(self._non_matching_item.error_description, "")
