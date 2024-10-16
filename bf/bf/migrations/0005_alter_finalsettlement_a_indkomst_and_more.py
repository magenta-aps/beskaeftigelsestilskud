# Generated by Django 5.0.4 on 2024-10-16 10:11

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bf', '0004_finalsettlement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='finalsettlement',
            name='a_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='alderspension',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='anden_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='andet_renteindtægt',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='anvendt_fradrag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='arbejdsmarkedsydelse',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='b_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='b_indkomst_andet',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='dis_gis',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='ejerandel_beløb',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='ejerandel_pct',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='ekstraordinære_indtægter',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_andet',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_bil',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_bolig',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_båd',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_internet',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_kost',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_logi',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='fri_telefon',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='frirejser',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='førtidspension',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='gruppeliv',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='indhandling',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='lejeindtægter_ved_udlejning',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='ligningsmæssig_fradrag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='lønindkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='netto_b_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='offentlig_hjælp',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='omsætning_salg_på_brættet',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='pensionsindbetaling',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='plejevederlag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteindtægter_bank',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteindtægter_obl',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteudgift_andet',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteudgift_bank',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteudgift_bsu',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteudgift_esu',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='renteudgift_realkredit',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='skattefri_b_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='skattemæssigt_resultat',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='skattepligtig_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='standard_fradrag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='tilskud_til_udenlandsk_pension',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='tjenestemandspension',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='udbytte_udenlandske',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='uddannelsesstøtte',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='udenlandsk_indkomst',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='udenlandsk_pensionsbidrag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='underholdsbidrag',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='virksomhedsrenter',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='virksomhedsrenter_indtægter',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='finalsettlement',
            name='virksomhedsrenter_udgifter',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='andre_b',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='brutto_b_før_erhvervsvirk_indhandling',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='brutto_b_indkomst',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='e2_indhandling',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='erhvervsindtægter_sum',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='honorarer',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='renteindtægter',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='uddannelsesstøtte',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearassessment',
            name='underholdsbidrag',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AlterField(
            model_name='personyearestimatesummary',
            name='mean_error_percent',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='personyearestimatesummary',
            name='rmse_percent',
            field=models.DecimalField(decimal_places=2, default=None, max_digits=12, null=True),
        ),
    ]
