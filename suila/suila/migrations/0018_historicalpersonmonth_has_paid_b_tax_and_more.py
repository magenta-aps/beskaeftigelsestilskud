# Generated by Django 5.1.3 on 2025-03-06 12:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "suila",
            "0017_alter_historicalpersonyear_preferred_estimation_engine_b_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalpersonmonth",
            name="has_paid_b_tax",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="historicalpersonyearassessment",
            name="latest",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="personmonth",
            name="has_paid_b_tax",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="personyearassessment",
            name="latest",
            field=models.BooleanField(default=True),
        ),
    ]
