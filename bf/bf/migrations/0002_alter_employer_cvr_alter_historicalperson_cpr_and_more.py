# Generated by Django 5.0.4 on 2024-06-21 14:56

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employer',
            name='cvr',
            field=models.PositiveIntegerField(db_index=True, unique=True, validators=[django.core.validators.MinValueValidator(1000000), django.core.validators.MaxValueValidator(99999999)], verbose_name='CVR-nummer'),
        ),
        migrations.AlterField(
            model_name='historicalperson',
            name='cpr',
            field=models.TextField(db_index=True, help_text='CPR nummer', max_length=10, validators=[django.core.validators.RegexValidator(regex='\\d{10}')], verbose_name='CPR nummer'),
        ),
        migrations.AlterField(
            model_name='person',
            name='cpr',
            field=models.TextField(help_text='CPR nummer', max_length=10, unique=True, validators=[django.core.validators.RegexValidator(regex='\\d{10}')], verbose_name='CPR nummer'),
        ),
        migrations.AlterUniqueTogether(
            name='personmonth',
            unique_together={('person_year', 'month')},
        ),
    ]
