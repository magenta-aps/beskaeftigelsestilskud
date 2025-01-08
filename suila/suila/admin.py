# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib import admin

from suila.models import PrismeAccountAlias


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
