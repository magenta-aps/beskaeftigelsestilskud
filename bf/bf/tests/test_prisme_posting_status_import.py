# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.test.utils import override_settings

from bf.integrations.prisme.posting_status import PostingStatus, PostingStatusImport
from bf.models import PersonMonth, PrismeBatch, PrismeBatchItem
from bf.tests.helpers import ImportTestCase

_EXAMPLE_1 = "§15;3112700000;00587075;9700;2021/04/09;RJ00;JKH Tesst;§15-000000059;"
_EXAMPLE_2 = "§15;3112700000;01587075;9700;2021/04/09;RJ00;JKH Tesst;§15-000000059;"


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


class TestPostingStatusImport(ImportTestCase):
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
