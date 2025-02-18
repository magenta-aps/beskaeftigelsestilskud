# Generated by Django 5.1.3 on 2025-02-18 07:09

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0006_alter_person_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalpersonyearassessment",
            name="valid_from",
            field=models.DateTimeField(default=datetime.datetime(1900, 1, 1, 0, 0)),
        ),
        migrations.AddField(
            model_name="personyearassessment",
            name="valid_from",
            field=models.DateTimeField(default=datetime.datetime(1900, 1, 1, 0, 0)),
        ),
    ]
