# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Any

from django.forms import RegexField
from django.utils.translation import gettext_lazy as _


class CPRField(RegexField):
    default_error_messages = {
        "required": _("Dette felt er påkrævet"),
        "invalid": _("Har du indtastet et korrekt CPR-nr.?"),
    }

    def __init__(self, **kwargs):
        super().__init__(r"^\d{6}-{0,1}\d{4}$", **kwargs)

    def to_python(self, raw_value: Any) -> str:
        value: str = super().to_python(raw_value)  # type: ignore
        # Remove dash in CPR, if given
        value = value.strip()
        if "-" in value:
            value = value.replace("-", "")
        return value
