# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.http import HttpRequest
from django.template.defaultfilters import register
from django.urls import ResolverMatch, resolve


@register.filter
def is_current_url(request: HttpRequest, view_name: str) -> str:
    match: ResolverMatch = resolve(request.path_info)
    if match.view_name == view_name:
        return "active"
    return ""
