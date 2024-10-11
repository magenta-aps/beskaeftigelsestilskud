# Generated by Django 5.0.4 on 2024-10-11 11:55

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0003_alter_incomeestimate_engine_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinalSettlement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('lønindkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('offentlig_hjælp', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('tjenestemandspension', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('alderspension', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('førtidspension', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('arbejdsmarkedsydelse', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('udenlandsk_pensionsbidrag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('tilskud_til_udenlandsk_pension', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('dis_gis', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('anden_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteindtægter_bank', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteindtægter_obl', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('andet_renteindtægt', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('uddannelsesstøtte', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('plejevederlag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('underholdsbidrag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('udbytte_udenlandske', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('udenlandsk_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('frirejser', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('gruppeliv', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('lejeindtægter_ved_udlejning', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('b_indkomst_andet', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_kost', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_logi', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_bolig', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_telefon', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_bil', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_internet', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_båd', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('fri_andet', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteudgift_realkredit', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteudgift_bank', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteudgift_esu', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteudgift_bsu', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('renteudgift_andet', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('pensionsindbetaling', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('omsætning_salg_på_brættet', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('indhandling', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('ekstraordinære_indtægter', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('virksomhedsrenter', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('virksomhedsrenter_indtægter', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('virksomhedsrenter_udgifter', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('skattemæssigt_resultat', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('ejerandel_pct', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('ejerandel_beløb', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('a_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('b_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('skattefri_b_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('netto_b_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('standard_fradrag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('ligningsmæssig_fradrag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('anvendt_fradrag', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('skattepligtig_indkomst', models.DecimalField(decimal_places=2, default=None, max_digits=10, null=True)),
                ('person_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='final_statements', to='bf.personyear')),
            ],
        ),
    ]
