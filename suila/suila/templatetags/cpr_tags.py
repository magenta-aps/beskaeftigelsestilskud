# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.defaultfilters import register


@register.filter
def format_cpr(cpr: str) -> str:
    return f"{cpr[0:6]}-{cpr[6:10]}"
