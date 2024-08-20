# Generated by Django 5.0.4 on 2024-08-16 09:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0002_alter_historicalperson_preferred_estimation_engine_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='personyearestimatesummary',
            name='offset_percent',
        ),
        migrations.AddField(
            model_name='personyearestimatesummary',
            name='mean_error_percent',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='personyearestimatesummary',
            name='rmse_percent',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True),
        ),
    ]
