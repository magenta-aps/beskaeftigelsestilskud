# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from contextlib import contextmanager
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from bf.integrations.prisme.posting_status import PostingStatus, PostingStatusImport
from bf.models import (
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    Year,
)

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

    def test_from_csv_buf(self):
        buf: BytesIO = BytesIO(_EXAMPLE_1.encode())
        rows = PostingStatus.from_csv_buf(buf)
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0], PostingStatus)

    def test_parse_date_raises_exception_on_invalid_input(self):
        with self.assertRaises(ValueError):
            PostingStatus._parse_date("")


class TestPostingStatusImport(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # This item has an invoice number matching the invoice number in the mocked
        # "posting status" CSV file, and should be considered "failed to post."
        cls._item_on_posting_status_list = cls._add_prisme_batch_item(
            cls._add_person_month(311270_0000),
            "00587075",
        )
        # This item has an invoice number which is not present in the mocked "posting
        # status" CSV file, and should be considered "succeeded to post."
        cls._item_not_on_posting_status_list = cls._add_prisme_batch_item(
            cls._add_person_month(311271_0000),
            "12345678",
        )

    @classmethod
    def _add_prisme_batch_item(
        self,
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

    @classmethod
    def _add_person_month(
        self,
        cpr: int,
        year: int = 2020,
        month: int = 1,
    ) -> PersonMonth:
        year, _ = Year.objects.get_or_create(year=year)
        person, _ = Person.objects.get_or_create(cpr=cpr)
        person_year, _ = PersonYear.objects.get_or_create(year=year, person=person)
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=person_year, month=month, import_date=date.today()
        )
        return person_month

    @contextmanager
    def _mock_sftp_server(self, *files):
        with patch(
            "bf.integrations.prisme.posting_status.list_prisme_folder",
            # This causes N calls to `get_file_in_prisme_folder` to be made, where N is
            # the length of `files`.
            return_value=[f"filename{i}.csv" for i, _ in enumerate(files, start=1)],
        ):
            with patch(
                "bf.integrations.prisme.posting_status.get_file_in_prisme_folder",
                # On each call to `get_file_in_prisme_folder`, provide a new return
                # value from this iterable.
                side_effect=[BytesIO(file.encode()) for file in files],
            ):
                yield

    def test_import_posting_status_is_idempotent(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)

        # First run
        with self._mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2):
            instance.import_posting_status(MagicMock(), 1)
        # First run creates the expected item statuses
        self._assert_expected_item_statuses()

        # Second run
        with self._mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2):
            instance.import_posting_status(MagicMock(), 1)
        # Second run: result is identical to first run
        self._assert_expected_item_statuses()

    def test_import_posting_status_verbosity_2(self):
        # Arrange
        stdout = MagicMock()
        instance = PostingStatusImport(2020, 1)
        with self._mock_sftp_server(_EXAMPLE_1):
            # Act
            instance.import_posting_status(stdout, 2)
        # Assert
        self.assertEqual(stdout.write.call_count, 4)

    def test_get_new_filenames(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)
        # Arrange: add `PrismeBatchItem` indicating that we have already loaded
        # `filename1.csv`.
        self._add_prisme_batch_item(
            self._add_person_month(311272_0000),
            "1234",
            "filename1.csv",
        )
        # Act
        with self._mock_sftp_server(_EXAMPLE_1):
            new_filenames: set[str] = instance._get_new_filenames()
        # Assert
        self.assertSetEqual(new_filenames, set())

    @override_settings(PRISME={"posting_status_folder": "foo"})
    def test_get_remote_folder_name(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)
        # Act and assert
        self.assertEqual(instance._get_remote_folder_name(), "foo")

    def test_load_file(self):
        # Arrange
        instance = PostingStatusImport(2020, 1)
        with self._mock_sftp_server(_EXAMPLE_1):
            # Act
            result: list[PostingStatus] = instance._load_file("filename1.csv")
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
