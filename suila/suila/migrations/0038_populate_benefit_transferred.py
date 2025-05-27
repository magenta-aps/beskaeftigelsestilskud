# Ceated by Nick on 2025-05-26
from django.db import migrations
from django.db.models import Sum
from common.model_utils import get_amount_from_g68_content


def populate_benefit_transferred(apps, schema_editor):

    model = apps.get_model("suila", "PersonMonth")

    for person_month in model.objects.all():
        if hasattr(person_month, "prismebatchitem"):

            # We use the get_amount_from_g68_content function because using a
            # property (prismebatchitem.amount) is not allowed in a migration
            person_month.benefit_transferred = get_amount_from_g68_content(
                person_month.prismebatchitem.g68_content
            )
            person_month.save()


def populate_prior_benefit_transferred(apps, schema_editor):

    model = apps.get_model("suila", "PersonMonth")
    for person_month in model.objects.all():

        month = person_month.month
        year = person_month.person_year.year.year
        person_pk = person_month.person_year.person.pk

        prior_benefit_transferred = model.objects.filter(
            month__lt=month,
            person_year__year__year=year,
            person_year__person__pk=person_pk,
        ).aggregate(total=Sum("benefit_transferred"))["total"]

        if prior_benefit_transferred:
            person_month.prior_benefit_transferred = prior_benefit_transferred
            person_month.save()


class Migration(migrations.Migration):

    dependencies = [
        (
            "suila",
            "0037_remove_historicalpersonmonth_prior_benefit_calculated_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(populate_benefit_transferred),
        migrations.RunPython(populate_prior_benefit_transferred),
    ]
