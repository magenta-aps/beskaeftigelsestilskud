# Generated by Django 5.0.4 on 2024-11-07 13:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bf", "0007_monthlyaincomereport_alimony_income_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrismeAccountAlias",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("alias", models.TextField(unique=True)),
                ("tax_municipality_location_code", models.TextField()),
                ("tax_year", models.PositiveSmallIntegerField()),
            ],
            options={
                "unique_together": {("tax_municipality_location_code", "tax_year")},
            },
        ),
    ]
