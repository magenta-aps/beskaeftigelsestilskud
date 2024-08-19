# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from urllib.parse import urlencode

from django.template.defaultfilters import register
from project.util import params_no_none


@register.filter
def urlparams(value: dict) -> str:
    return urlencode(params_no_none(value))
