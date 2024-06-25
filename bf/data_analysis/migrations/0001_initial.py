# Generated by Django 5.0.4 on 2024-06-25 06:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bf', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CalculationResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('engine', models.CharField(choices=[('InYearExtrapolationEngine', 'Ekstrapolation af beløb for måneder i indeværende år'), ('TwelveMonthsSummationEngine', 'Summation af beløb for de seneste 12 måneder')], max_length=100)),
                ('calculated_year_result', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('actual_year_result', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('a_salary_report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='bf.AIncomeReport')),
            ],
        ),
    ]
