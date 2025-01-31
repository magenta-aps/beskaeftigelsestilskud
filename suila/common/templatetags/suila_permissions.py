# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth.models import User
from django.template.defaultfilters import register


@register.filter
def has_permissions(user: User, permissions: str) -> bool:
    permission_names: list[str] = permissions.split(",")
    return all(user.has_perm(perm) for perm in permission_names)
