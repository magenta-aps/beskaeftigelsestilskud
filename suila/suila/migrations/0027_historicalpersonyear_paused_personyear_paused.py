# Generated by Django 5.1.3 on 2025-04-04 07:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "suila",
            "0026_alter_historicalpersonyear_preferred_estimation_engine_u_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalpersonyear",
            name="paused",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="personyear",
            name="paused",
            field=models.BooleanField(default=False),
        ),
    ]
