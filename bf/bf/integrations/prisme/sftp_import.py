# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from io import BytesIO

from django.conf import settings
from tenQ.client import get_file_in_prisme_folder, list_prisme_folder


class SFTPImport:
    def get_remote_folder_name(self) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_new_filenames(self, known_filenames: set[str]) -> set[str]:
        remote_filenames: set[str] = set(
            list_prisme_folder(
                settings.PRISME,  # type: ignore[misc]
                self.get_remote_folder_name(),
            )
        )
        new_filenames: set[str] = remote_filenames - known_filenames
        return new_filenames

    def get_file(self, filename: str) -> BytesIO:
        buf: BytesIO = get_file_in_prisme_folder(
            settings.PRISME,  # type: ignore[misc]
            self.get_remote_folder_name(),
            filename,
        )
        return buf
