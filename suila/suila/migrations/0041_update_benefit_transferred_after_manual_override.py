# Ceated by Nick on 2025-05-26
from django.db import migrations


def update_benefit_transferred(apps, schema_editor):
    PersonMonth = apps.get_model("suila", "PersonMonth")

    # Get all person-months which have a prisme-item BUT have benefit_calculated = 0kr
    # These are persons for whom we manually set benefit_paid to 0.
    # This queryset returns 2 persons
    person_months = PersonMonth.objects.filter(
        person_year__year__year=2025,
        prismebatchitem__isnull=False,
        benefit_calculated=0,
    )

    for person_month in person_months:
        person_month.benefit_transferred = 0
        person_month.save()


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0040_prismepostingstatusfile_and_more"),
    ]

    operations = [
        migrations.RunPython(update_benefit_transferred),
    ]
