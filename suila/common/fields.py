# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Any

from django.forms import RegexField


class CPRField(RegexField):
    def __init__(self, **kwargs):
        super().__init__(r"^\d{6}-{0,1}\d{4}$", **kwargs)

    def to_python(self, raw_value: Any) -> str:
        value: str = super().to_python(raw_value)
        # Remove dash in CPR, if given
        value = value.strip()
        if "-" in value:
            value = value.replace("-", "")
        return value
