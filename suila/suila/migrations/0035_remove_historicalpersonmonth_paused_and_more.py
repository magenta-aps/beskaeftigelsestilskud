# Generated by Django 5.1.3 on 2025-05-23 11:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "suila",
            "0034_rename_benefit_paid_historicalpersonmonth_benefit_calculated_and_more",
        ),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalpersonmonth",
            name="paused",
        ),
        migrations.RemoveField(
            model_name="personmonth",
            name="paused",
        ),
    ]
