# Generated by Django 5.1.3 on 2024-12-18 12:09

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bf", "0023_fix_prisme_account_aliases"),
    ]

    operations = [
        migrations.CreateModel(
            name="EboksMessage",
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
                ("created", models.DateTimeField(auto_now_add=True)),
                ("sent", models.DateTimeField(null=True)),
                ("xml", models.BinaryField()),
                (
                    "cpr_cvr",
                    models.CharField(
                        validators=[django.core.validators.RegexValidator("\\d{8,10}")]
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("content_type", models.IntegerField()),
                ("message_id", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Genereret"),
                            ("sent", "Afsendt"),
                            ("post_processing", "Afventer efterbehandling"),
                            ("failed", "Afsendelse fejlet"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "recipient_status",
                    models.CharField(
                        choices=[
                            ("", "Gyldig E-boks modtager"),
                            ("exempt", "Fritaget modtager"),
                            (
                                "invalid",
                                "Ugyldig E-boks modtager (sendes til efterbehandling)",
                            ),
                            ("dead", "Afdød"),
                            ("minor", "Mindreårig"),
                        ],
                        max_length=8,
                    ),
                ),
                (
                    "post_processing_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", ""),
                            ("pending", "Afventer processering"),
                            ("address resolved", "Fundet gyldig postadresse"),
                            ("address not found", "Ingen gyldig postadresse"),
                            ("remote printed", "Overført til fjernprint"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                (
                    "is_postprocessing",
                    models.BooleanField(db_index=True, default=False),
                ),
            ],
        ),
    ]