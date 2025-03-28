# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.response import TemplateResponse

HONEYPOT_FIELD_NAME = "phone_number"


def HONEYPOT_RESPONDER(request, context):
    return TemplateResponse(
        request=request,
        status=403,
        template="403.html",
    )
