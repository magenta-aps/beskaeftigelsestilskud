# Generated by Django 5.1.3 on 2025-03-07 08:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0019_historicalpersonyear_b_expenses_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalmonthlyincomereport",
            name="b_income",
        ),
        migrations.RemoveField(
            model_name="monthlyincomereport",
            name="b_income",
        ),
    ]
