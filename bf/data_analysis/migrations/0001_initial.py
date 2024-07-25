# Generated by Django 5.0.4 on 2024-07-24 12:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bf', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IncomeEstimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('engine', models.CharField(choices=[('InYearExtrapolationEngine', 'Ekstrapolation af beløb for måneder i indeværende år'), ('TwelveMonthsSummationEngine', 'Summation af beløb for de seneste 12 måneder')], max_length=100)),
                ('estimated_year_result', models.DecimalField(decimal_places=2, max_digits=12)),
                ('actual_year_result', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('person_month', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='bf.personmonth')),
            ],
            options={
                'unique_together': {('engine', 'person_month')},
            },
        ),
        migrations.CreateModel(
            name='PersonYearEstimateSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estimation_engine', models.CharField(max_length=100)),
                ('offset_percent', models.DecimalField(decimal_places=2, max_digits=10)),
                ('person_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.personyear')),
            ],
            options={
                'unique_together': {('person_year', 'estimation_engine')},
            },
        ),
    ]
