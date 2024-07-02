# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from urllib.parse import urlencode

from django.template.defaultfilters import register


@register.filter
def urlparams(value: dict):
    return urlencode(value)
