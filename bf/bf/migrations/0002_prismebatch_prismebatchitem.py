# Generated by Django 5.0.4 on 2024-09-26 14:18

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrismeBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed')], db_index=True, default='sending')),
                ('failed_message', models.TextField()),
                ('export_date', models.DateField(db_index=True)),
                ('prefix', models.IntegerField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='PrismeBatchItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('g68_content', models.TextField()),
                ('g69_content', models.TextField()),
                ('person_month', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='bf.personmonth')),
                ('prisme_batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bf.prismebatch')),
            ],
            options={
                'unique_together': {('prisme_batch', 'person_month')},
            },
        ),
    ]
