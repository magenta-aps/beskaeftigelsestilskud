# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import os.path
import time
import urllib
import urllib.parse
from contextlib import ContextDecorator
from typing import TYPE_CHECKING
from uuid import uuid4

import requests
from django.conf import settings
from requests.exceptions import RequestException

if TYPE_CHECKING:  # pragma: no cover
    from suila.models import EboksMessage


class MessageFailureException(Exception):
    def __init__(self, message_id: str, message: "EboksMessage", cause: Exception):
        super().__init__(f"Message id {message_id} already exists on server")
        self.message_id = message_id
        self.message = message
        self.cause = cause


class MessageCollisionException(MessageFailureException):
    pass


class EboksClient(ContextDecorator):
    def __init__(
        self,
        client_certificate,
        client_private_key,
        verify,
        client_id,
        system_id,
        host,
        timeout=60,
    ):
        if not os.path.isfile(client_certificate):
            raise FileNotFoundError(
                f"Configured file '{client_certificate}' does not exist.'"
            )
        if not os.path.isfile(client_private_key):
            raise FileNotFoundError(
                f"Configured file '{client_private_key}' does not exist.'"
            )
        self.client_id = client_id
        self.system_id = str(system_id)
        self.host = host
        self.timeout = timeout
        self.session = requests.session()
        self.session.cert = (client_certificate, client_private_key)
        self.verify = verify
        if verify:
            self.session.verify = verify
        self.session.headers.update({"content-type": "application/xml"})
        self.url_with_prefix = urllib.parse.urljoin(self.host, "/int/rest/srv.svc/")

    @staticmethod
    def from_settings():
        eboks_settings = settings.EBOKS
        return EboksClient(
            eboks_settings["client_cert"],
            eboks_settings["client_key"],
            eboks_settings["host_verify"],
            eboks_settings["client_id"],
            eboks_settings["system_id"],
            eboks_settings["host"],
            eboks_settings["timeout"],
        )

    def _make_request(self, url, method="GET", params=None, data=None):
        r = self.session.request(method, url, params, data, timeout=self.timeout)
        r.raise_for_status()
        return r

    def get_client_info(self):
        url = urllib.parse.urljoin(
            self.host, "/rest/client/{client_id}/".format(client_id=self.client_id)
        )
        return self._make_request(url=url)

    def get_recipient_status(self, message_ids):
        url = urllib.parse.urljoin(
            self.host, "/rest/messages/{client_id}/".format(client_id=self.client_id)
        )
        return self._make_request(url=url, params={"message_id": message_ids})

    def get_message_id(self):
        return "{sys_id}{client_id}{uuid}".format(
            sys_id=self.system_id.zfill(6), client_id=self.client_id, uuid=uuid4().hex
        )

    def send_message(self, message: "EboksMessage", message_id: str, retries: int = 0):
        url = urllib.parse.urljoin(
            self.url_with_prefix,
            "3/dispatchsystem/{sys_id}/dispatches/{message_id}".format(
                sys_id=self.system_id, message_id=message_id
            ),
        )
        try:
            return self._make_request(url=url, method="PUT", data=message.xml)
        except RequestException as e:
            if e.response is not None:
                if e.response.status_code == 419:
                    raise MessageCollisionException(message_id, message, e)
                if e.response.status_code == 400:
                    raise MessageFailureException(message_id, message, e)
            if retries > 0:
                time.sleep(10)
                message_id = self.get_message_id()
                return self.send_message(message, message_id, retries - 1)
            else:
                raise MessageFailureException(message_id, message, e)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
