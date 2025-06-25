# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from suila.models import PrismeAccountAlias, User


@admin.register(PrismeAccountAlias)
class PrismeAccountAliasAdmin(admin.ModelAdmin):
    list_display = [
        "tax_municipality_location_code",
        "tax_year",
        "alias",
        "tax_municipality_five_digit_code",
    ]
    ordering = [
        "tax_municipality_location_code",
        "tax_year",
        "alias",
    ]
    list_filter = [
        "tax_municipality_location_code",
        "tax_year",
    ]
    search_fields = ["alias__icontains"]


# Register our own model admin for possible customization
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass
