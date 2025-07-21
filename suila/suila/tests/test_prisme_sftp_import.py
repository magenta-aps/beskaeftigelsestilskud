# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import BytesIO
from unittest.mock import ANY, patch

from django.conf import settings
from tenQ.client import ClientException

from suila.integrations.prisme.sftp_import import SFTPImport
from suila.tests.helpers import ImportTestCase


class SampleSFTPImport(SFTPImport):
    def get_remote_folder_name(self) -> str:
        return "sample"

    def get_known_filenames(self) -> set[str]:
        return {"filename1.csv"}


class TestSFTPImport(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.instance = SampleSFTPImport()

    def test_get_new_filenames(self):
        # Arrange: this mocks an SFTP server with files called `filename1.csv`,
        # `filename2.csv`, and `filename3.csv`.
        with self.mock_sftp_server("1", "2", "3"):
            # Act
            result: set[str] = self.instance.get_new_filenames()
            # Assert: the new filenames are `filename2.csv` and `filename3.csv`, as
            # `SampleSFTPImport.get_known_filenames` returns `{"filename1.csv"}`.
            self.assertEqual(result, {f"filename{i}.csv" for i in (2, 3)})

    def test_get_file(self):
        with self.mock_sftp_server("1"):
            buf: BytesIO = self.instance.get_file("filename1.csv")
            self.assertEqual(buf.getvalue(), "1".encode(self.encoding))

    def test_get_file_retries_on_failure(self):
        with patch(
            "suila.integrations.prisme.sftp_import.get_file_in_prisme_folder",
            side_effect=ClientException("Uh-oh"),
        ) as mock_get:
            # Act
            with self.assertRaises(ClientException):
                self.instance.get_file("filename1.csv")
            # Assert: the download function is called multiple times, until
            # giving up.
            mock_get.assert_called_with(
                settings.PRISME,
                ANY,  # `remote_folder`
                "filename1.csv",
            )
            self.assertEqual(mock_get.call_count, 10)  # 10 retry attempts

    def test_get_remote_folder_filenames_retries_on_failure(self):
        with patch(
            "suila.integrations.prisme.sftp_import.list_prisme_folder",
            side_effect=ClientException("Uh-oh"),
        ) as mock_get:
            # Act
            with self.assertRaises(ClientException):
                self.instance._get_remote_folder_filenames()
            # Assert: the function is called multiple times, until giving up
            mock_get.assert_called_with(
                settings.PRISME,
                ANY,  # `remote_folder`
            )
            self.assertEqual(mock_get.call_count, 10)  # 10 retry attempts
