# Generated by Django 5.1.3 on 2025-07-17 14:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "suila",
            "0045_alter_standardworkbenefitcalculationmethod_benefit_rate_percent_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="prismebatch",
            name="prefix",
            field=models.BigIntegerField(db_index=True),
        ),
    ]
