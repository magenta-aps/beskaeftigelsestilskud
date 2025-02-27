# Generated by Django 5.1.3 on 2025-02-27 09:35

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0010_historicalpersonyearassessment_benefits_income_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalperson",
            name="welcome_letter",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="suila.eboksmessage",
            ),
        ),
        migrations.AddField(
            model_name="historicalperson",
            name="welcome_letter_sent_at",
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="person",
            name="welcome_letter",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="suila.eboksmessage",
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="welcome_letter_sent_at",
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
