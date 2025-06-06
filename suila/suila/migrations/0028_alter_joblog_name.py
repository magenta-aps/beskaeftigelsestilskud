# Generated by Django 5.1.3 on 2025-04-22 11:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0027_historicalpersonyear_paused_personyear_paused"),
    ]

    operations = [
        migrations.AlterField(
            model_name="joblog",
            name="name",
            field=models.TextField(
                choices=[
                    ("calculate_stability_score", "Calculate Stability Score"),
                    ("autoselect_estimation_engine", "Autoselect Estimation Engine"),
                    ("load_eskat", "Load Eskat"),
                    ("load_prisme_b_tax", "Load Prisme B Tax"),
                    ("import_u1a_data", "Import U1A Data"),
                    ("get_person_info_from_dafo", "Get Person Info From Dafo"),
                    ("estimate_income", "Estimate Income"),
                    ("calculate_benefit", "Calculate Benefit"),
                    ("export_benefits_to_prisme", "Export Benefits To Prisme"),
                    ("eboks_send", "Send Eboks"),
                ]
            ),
        ),
    ]
