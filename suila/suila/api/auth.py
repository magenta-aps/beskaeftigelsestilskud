# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
import re
from typing import List, Tuple
from urllib.parse import unquote

from common.models import User
from django.http import HttpRequest
from ninja.security.base import AuthBase
from ninja_extra import ControllerBase, permissions


class RestPermission(permissions.BasePermission):
    method_map = {
        "GET": "view",
        "POST": "add",
        "PATCH": "change",
        "DELETE": "delete",
    }
    appname: str
    modelname: str

    def has_permission(self, request: HttpRequest, controller: ControllerBase) -> bool:
        method = str(request.method)
        operation = self.method_map[method]
        return request.user.has_perm(f"{self.appname}.{operation}_{self.modelname}")


class ClientCertAuth(AuthBase):

    openapi_type: str = "mutualTLS"
    cert_info_header = "X-Forwarded-Tls-Client-Cert-Info"

    def __call__(self, request: HttpRequest) -> User | None:
        subject = self.get_subject(request)
        if subject is not None:
            user = self.authenticate(subject)
            if user is not None:
                request.user = user
                return user
        return None

    @classmethod
    def get_info(cls, request: HttpRequest) -> List[Tuple[str, str]] | None:
        info = request.headers.get(cls.cert_info_header)
        if info is not None:
            info = unquote(info)
            items = []
            for part in re.findall(r'\w+="[^"]*"', info):
                eq_index = part.index("=")
                key: str = part[0:eq_index]
                value: str = part[eq_index + 1 :].strip('"')
                items.append((key, value))
            return items
        return None

    @staticmethod
    def get_subject(request: HttpRequest) -> str | None:
        info = ClientCertAuth.get_info(request)
        if info is not None and len(info) > 0:
            for part in info:
                if part[0] == "Subject":
                    return part[1]
        return None

    def authenticate(self, subject: str) -> User | None:
        try:
            return User.objects.get(cert_subject=subject)
        except User.DoesNotExist:
            return None


def get_auth_methods():
    """This function defines the authentication methods available for this API."""
    return (ClientCertAuth(),)
