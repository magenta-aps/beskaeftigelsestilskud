# Generated by Django 5.1.3 on 2024-11-18 07:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bf", "0012_remove_historicalfinalbincomereport_history_relation_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalpersonyear",
            name="tax_scope",
            field=models.CharField(
                choices=[
                    ("FULD", "Fuldt Skattepligtig"),
                    ("DELVIS", "Delvist Skattepligtig"),
                    ("INGEN_MANDTAL", "Forsvundet Fra Mandtal"),
                ],
                default="FULD",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="personyear",
            name="tax_scope",
            field=models.CharField(
                choices=[
                    ("FULD", "Fuldt Skattepligtig"),
                    ("DELVIS", "Delvist Skattepligtig"),
                    ("INGEN_MANDTAL", "Forsvundet Fra Mandtal"),
                ],
                default="FULD",
                max_length=20,
            ),
        ),
    ]