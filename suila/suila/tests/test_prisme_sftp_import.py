# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import BytesIO

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
            self.assertEqual(buf.getvalue(), b"1")
