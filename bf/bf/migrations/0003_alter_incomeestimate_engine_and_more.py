# Generated by Django 5.0.4 on 2024-09-27 13:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0002_prismebatch_prismebatchitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='incomeestimate',
            name='engine',
            field=models.CharField(choices=[('InYearExtrapolationEngine', 'Ekstrapolation af beløb for måneder i indeværende år'), ('TwelveMonthsSummationEngine', 'Summation af beløb for de seneste 12 måneder'), ('TwoYearSummationEngine', 'Summation af beløb for de seneste 24 måneder'), ('SameAsLastMonthEngine', 'Ekstrapolation af beløb for den seneste måned'), ('SelfReportedEngine', 'Estimering udfra forskudsopgørelsen')], max_length=100),
        ),
        migrations.AlterField(
            model_name='personyear',
            name='preferred_estimation_engine_a',
            field=models.CharField(choices=[('InYearExtrapolationEngine', 'Ekstrapolation af beløb for måneder i indeværende år'), ('TwelveMonthsSummationEngine', 'Summation af beløb for de seneste 12 måneder'), ('TwoYearSummationEngine', 'Summation af beløb for de seneste 24 måneder'), ('SameAsLastMonthEngine', 'Ekstrapolation af beløb for den seneste måned'), ('SelfReportedEngine', 'Estimering udfra forskudsopgørelsen')], default='InYearExtrapolationEngine', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='personyear',
            name='preferred_estimation_engine_b',
            field=models.CharField(choices=[('InYearExtrapolationEngine', 'Ekstrapolation af beløb for måneder i indeværende år'), ('TwelveMonthsSummationEngine', 'Summation af beløb for de seneste 12 måneder'), ('TwoYearSummationEngine', 'Summation af beløb for de seneste 24 måneder'), ('SameAsLastMonthEngine', 'Ekstrapolation af beløb for den seneste måned'), ('SelfReportedEngine', 'Estimering udfra forskudsopgørelsen')], default='InYearExtrapolationEngine', max_length=100, null=True),
        ),
    ]