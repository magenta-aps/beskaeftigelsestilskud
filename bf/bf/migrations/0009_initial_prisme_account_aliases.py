# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools

from django.db import migrations


AFDELING = "100045"
FINANSLOV = "240614"
FORMAAL = "0101010000"
ART = "242040195"

MUNICIPALITY_CODES = [
    ("010300", "955"),  # Kommune Kujalleq           31 (eSkat) og 010300 (Prisme SEL)
    ("010400", "956"),  # Kommuneqarfik Sermersooq   32 (eSkat) og 010400 (Prisme SEL)
    ("010500", "957"),  # Qeqqata Kommunia           33 (eSkat) og 010500 (Prisme SEL)
    ("010600", "959"),  # Kommune Qeqertalik         36 (eSkat) og 010600 (Prisme SEL)
    ("010700", "960"),  # Avannaata Kommunia         37 (eSkat) og 010700 (Prisme SEL)
    ("010900", "961"),  # SDI (Skattestyrelsen)      20 (eSkat) og 010900 (Prisme SEL)
]

# Currently, account aliases are defined for the years 2025, 2026, 2027, 2029 and 2030
TAX_YEARS = range(2025, 2031)

def load_initial_prisme_account_aliases(apps, schema_editor):
    PrismeAccountAlias = apps.get_model("bf", "PrismeAccountAlias")
    objects: list[PrismeAccountAlias] = [
        PrismeAccountAlias(
            alias=f"{AFDELING}{FINANSLOV}{FORMAAL}{ART}{municipality_code[0]}{tax_year}",
            tax_municipality_location_code=municipality_code[1],
            tax_year=tax_year,
        )
        for municipality_code, tax_year
        in itertools.product(MUNICIPALITY_CODES, TAX_YEARS)
    ]
    PrismeAccountAlias.objects.bulk_create(objects)


class Migration(migrations.Migration):
    dependencies = [
        ("bf", "0008_prismeaccountalias"),
    ]

    operations = [
        migrations.RunPython(load_initial_prisme_account_aliases)
    ]
