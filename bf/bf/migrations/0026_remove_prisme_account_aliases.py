# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.db import migrations


def remove_prisme_account_aliases(apps, schema_editor):
    PrismeAccountAlias = apps.get_model("bf", "PrismeAccountAlias")
    PrismeAccountAlias.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("bf", "0025_alter_standardworkbenefitcalculationmethod_benefit_rate_percent_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_prisme_account_aliases)
    ]
