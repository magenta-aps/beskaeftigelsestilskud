# Generated by Django 5.1.3 on 2025-03-04 10:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0015_alter_annualincome_account_share_business_amount_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="btaxpayment",
            name="person_month",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="suila.personmonth",
            ),
        ),
    ]
