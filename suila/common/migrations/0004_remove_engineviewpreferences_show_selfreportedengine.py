# Generated by Django 5.1.3 on 2025-03-07 13:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "common",
            "0003_remove_engineviewpreferences_show_sameaslastmonthengine_and_more",
        ),
    ]

    operations = [
        migrations.RemoveField(
            model_name="engineviewpreferences",
            name="show_SelfReportedEngine",
        ),
    ]
