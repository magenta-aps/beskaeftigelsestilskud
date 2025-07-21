# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from io import BytesIO

from django.conf import settings
from tenacity import (
    after_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from tenQ.client import ClientException, get_file_in_prisme_folder, list_prisme_folder

logger = logging.getLogger(__name__)


class SFTPImport:
    retry_policy = retry(
        retry=retry_if_exception_type(ClientException),
        reraise=True,  # raise `ClientException` if final retry attempt fails
        stop=stop_after_attempt(10),
        wait=wait_fixed(1),  # 1 second before retry
        after=after_log(logger, logging.WARNING),  # log all retry attempts
    )

    def get_remote_folder_name(self) -> str:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_known_filenames(self) -> set[str]:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    def get_new_filenames(self) -> set[str]:
        known_filenames: set[str] = self.get_known_filenames()
        remote_filenames: set[str] = set(self._get_remote_folder_filenames())
        new_filenames: set[str] = remote_filenames - known_filenames
        return new_filenames

    @retry_policy
    def get_file(self, filename: str) -> BytesIO:
        buf: BytesIO = get_file_in_prisme_folder(
            settings.PRISME,  # type: ignore[misc]
            self.get_remote_folder_name(),
            filename,
        )
        return buf

    @retry_policy
    def _get_remote_folder_filenames(self):
        return list_prisme_folder(
            settings.PRISME,  # type: ignore[misc]
            self.get_remote_folder_name(),
        )
