# Generated by Django 5.0.4 on 2024-06-20 12:48

import django.core.validators
import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Employer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cvr', models.PositiveIntegerField(db_index=True, validators=[django.core.validators.MinValueValidator(1000000), django.core.validators.MaxValueValidator(99999999)], verbose_name='CVR-nummer')),
                ('name', models.CharField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cpr', models.TextField(help_text='CPR nummer', max_length=10, validators=[django.core.validators.RegexValidator(regex='\\d{10}')], verbose_name='CPR nummer')),
                ('name', models.TextField(blank=True, null=True)),
                ('address_line_1', models.TextField(blank=True, null=True)),
                ('address_line_2', models.TextField(blank=True, null=True)),
                ('address_line_3', models.TextField(blank=True, null=True)),
                ('address_line_4', models.TextField(blank=True, null=True)),
                ('address_line_5', models.TextField(blank=True, null=True)),
                ('full_address', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='PersonMonth',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('import_date', models.DateField(verbose_name='Dato')),
                ('municipality_code', models.IntegerField(blank=True, null=True)),
                ('municipality_name', models.TextField(blank=True, null=True)),
                ('fully_tax_liable', models.BooleanField(blank=True, null=True)),
                ('month', models.PositiveSmallIntegerField()),
                ('benefit_paid', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('estimated_year_benefit', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('prior_benefit_paid', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='StandardWorkBenefitCalculationMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('benefit_rate_percent', models.DecimalField(decimal_places=3, max_digits=5)),
                ('personal_allowance', models.DecimalField(decimal_places=2, max_digits=12)),
                ('standard_allowance', models.DecimalField(decimal_places=2, max_digits=12)),
                ('max_benefit', models.DecimalField(decimal_places=2, max_digits=12)),
                ('scaledown_rate_percent', models.DecimalField(decimal_places=3, max_digits=5)),
                ('scaledown_ceiling', models.DecimalField(decimal_places=2, max_digits=12)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='HistoricalPerson',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('history_change_reason', models.TextField(null=True)),
                ('cpr', models.TextField(help_text='CPR nummer', max_length=10, validators=[django.core.validators.RegexValidator(regex='\\d{10}')], verbose_name='CPR nummer')),
                ('name', models.TextField(blank=True, null=True)),
                ('address_line_1', models.TextField(blank=True, null=True)),
                ('address_line_2', models.TextField(blank=True, null=True)),
                ('address_line_3', models.TextField(blank=True, null=True)),
                ('address_line_4', models.TextField(blank=True, null=True)),
                ('address_line_5', models.TextField(blank=True, null=True)),
                ('full_address', models.TextField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('history_relation', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='history_entries', to='bf.person')),
            ],
            options={
                'verbose_name': 'historical person',
                'verbose_name_plural': 'historical persons',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='ASalaryReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('employer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.employer')),
                ('person_month', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.personmonth')),
            ],
        ),
        migrations.CreateModel(
            name='PersonYear',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.person')),
            ],
        ),
        migrations.AddField(
            model_name='personmonth',
            name='person_year',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.personyear'),
        ),
        migrations.CreateModel(
            name='Year',
            fields=[
                ('year', models.PositiveSmallIntegerField(primary_key=True, serialize=False)),
                ('calculation_method_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('calculation_method_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype')),
            ],
        ),
        migrations.AddField(
            model_name='personyear',
            name='year',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.year'),
        ),
        migrations.AddIndex(
            model_name='personmonth',
            index=models.Index(fields=['month'], name='bf_personmo_month_115b48_idx'),
        ),
        migrations.AddIndex(
            model_name='personmonth',
            index=models.Index(fields=['municipality_code'], name='bf_personmo_municip_8c1c35_idx'),
        ),
        migrations.AddIndex(
            model_name='personyear',
            index=models.Index(fields=['person', 'year'], name='bf_personye_person__6424e8_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='personyear',
            unique_together={('person', 'year')},
        ),
    ]
