# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
import tempfile

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from requests.exceptions import RequestException
from tenQ.client import ClientException, list_prisme_folder

from suila.integrations.eskat.client import EskatClient

logger = logging.getLogger(__name__)


def health_check_storage(request):
    try:
        with tempfile.NamedTemporaryFile(
            dir=settings.MEDIA_ROOT, delete=True
        ) as temp_file:
            test_content = b"Test"
            temp_file.write(test_content)
            temp_file.flush()
            temp_file.seek(0)

            content = temp_file.read()
            if content != test_content:
                raise ValueError(
                    (
                        "File content does not match, when trying to write and "
                        "read from file"
                    )
                )

        return HttpResponse("OK")
    except Exception:
        logger.exception("Storage health check failed")
        return HttpResponse("ERROR", status=500)


def health_check_database(request):
    try:
        connection.ensure_connection()
        return HttpResponse("OK")
    except Exception:
        logger.exception("Database health check failed")
        return HttpResponse("ERROR", status=500)


def health_check_sftp(request):
    try:
        list_prisme_folder(settings.PRISME, settings.PRISME["control_folder"])
        return HttpResponse("OK")
    except ClientException:
        logger.exception("SFTP health check failed")
        return HttpResponse("ERROR", status=500)


def health_check_eskat(request):
    try:
        client = EskatClient.from_settings()
        client.get_tax_scopes()
        return HttpResponse("OK")
    except RequestException:
        logger.exception("Eskat health check failed")
        return HttpResponse("ERROR", status=500)
