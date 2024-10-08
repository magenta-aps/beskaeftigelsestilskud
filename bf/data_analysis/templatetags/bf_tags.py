# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Any
from urllib.parse import urlencode

from django.template.defaultfilters import register
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrPromise
from project.util import params_no_none


@register.filter
def urlparams(value: dict) -> str:
    return urlencode(params_no_none(value))


@register.filter
def multiply(value1, value2):
    return value1 * value2


@register.filter
def concat(value1: str, value2: str):
    return f"{value1}{value2}"


@register.filter
def get(item: Any, attribute: str | int):
    if item is not None:
        if type(attribute) is str:
            if hasattr(item, attribute):
                return getattr(item, attribute)
            if hasattr(item, "get"):
                return item.get(attribute)
        if isinstance(item, (tuple, list)):
            index = int(attribute)
            if index < len(item):
                return item[index]
            return None
        if isinstance(item, dict):
            if str(attribute) in item:
                return item[str(attribute)]
        try:
            return item[attribute]
        except (KeyError, TypeError, IndexError):
            pass


@register.filter
def yesno(boolean: bool) -> StrPromise:
    return _("Ja") if boolean else _("Nej")
