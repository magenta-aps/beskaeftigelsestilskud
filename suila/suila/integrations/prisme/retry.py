# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from tenacity import RetryCallState


def retry_wait(retry_state: RetryCallState) -> float:
    """Number of seconds to wait between Prisme SFTP retry attempts.

    Looked up on every attempt rather than baked into the `wait_fixed` passed to
    the decorator, so that the test suite can drop it to zero instead of really
    sleeping through ten attempts.
    """
    return settings.PRISME_RETRY_WAIT_SECONDS  # type: ignore[misc]
