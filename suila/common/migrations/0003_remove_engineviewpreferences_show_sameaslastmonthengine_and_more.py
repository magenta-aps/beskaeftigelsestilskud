# Generated by Django 5.1.3 on 2025-02-28 13:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0002_pageview_itemview"),
    ]

    operations = [
        migrations.RenameField(
            model_name="engineviewpreferences",
            old_name="show_SameAsLastMonthEngine",
            new_name="show_MonthlyContinuationEngine",
        ),
    ]
