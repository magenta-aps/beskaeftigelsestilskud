# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools

from django.db import migrations


AFDELING = "100045"
FINANSLOV = "240614"
FORMAAL = "101010000"
ART = "242040195"

MUNICIPALITY_CODES = [
    ("10300", "955"),  # Kommune Kujalleq           31 (eSkat) og 010300 (Prisme SEL)
    ("10400", "956"),  # Kommuneqarfik Sermersooq   32 (eSkat) og 010400 (Prisme SEL)
    ("10500", "957"),  # Qeqqata Kommunia           33 (eSkat) og 010500 (Prisme SEL)
    ("10600", "959"),  # Kommune Qeqertalik         36 (eSkat) og 010600 (Prisme SEL)
    ("10700", "960"),  # Avannaata Kommunia         37 (eSkat) og 010700 (Prisme SEL)
    ("10900", "961"),  # SDI (Skattestyrelsen)      20 (eSkat) og 010900 (Prisme SEL)
]

# Currently, account aliases are defined for the years 2025, 2026, 2027, 2029 and 2030
TAX_YEARS = range(2025, 2031)


def update_prisme_account_aliases(apps, schema_editor):
    PrismeAccountAlias = apps.get_model("suila", "PrismeAccountAlias")
    objects: list[PrismeAccountAlias] = [
        PrismeAccountAlias(
            alias=f"{AFDELING}{FINANSLOV}{FORMAAL}{ART}{municipality_code[0]}{tax_year - 2000}",
            tax_municipality_location_code=municipality_code[1],
            tax_year=tax_year,
        )
        for municipality_code, tax_year
        in itertools.product(MUNICIPALITY_CODES, TAX_YEARS)
    ]
    return PrismeAccountAlias.objects.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["tax_municipality_location_code", "tax_year"],
        update_fields=["alias"],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0001_initial"),
    ]

    operations = []
