# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.defaultfilters import register


@register.filter
def format_cpr(cpr: str | int) -> str:
    if isinstance(cpr, int):
        cpr = f"{cpr:10}"
    return f"{cpr[0:6]}-{cpr[6:10]}"
