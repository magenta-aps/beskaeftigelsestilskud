# Ceated by Nick on 2025-05-26
from django.db import migrations
from common.model_utils import get_amount_from_g68_content
import logging
from django.db import transaction
from django.db.models import Prefetch

logger = logging.getLogger(__name__)


def populate_benefit_transferred(apps, schema_editor):
    model = apps.get_model("suila", "PersonMonth")
    logger.info("Populating person_month.benefit_transferred")

    person_months = model.objects.filter(
        person_year__year__year=2025,
        prismebatchitem__isnull=False,
    ).select_related("prismebatchitem")

    total_person_months = person_months.count()

    with transaction.atomic():
        for counter, person_month in enumerate(person_months, start=1):
            logger.info(f"Processing person_month {counter}/{total_person_months}")

            # We use the get_amount_from_g68_content function because using a
            # property (prismebatchitem.amount) is not allowed in a migration
            person_month.benefit_transferred = get_amount_from_g68_content(
                person_month.prismebatchitem.g68_content
            )
            person_month.save(update_fields=["benefit_transferred"])


def populate_prior_benefit_transferred(apps, schema_editor):
    PersonYear = apps.get_model("suila", "PersonYear")
    PersonMonth = apps.get_model("suila", "PersonMonth")
    logger.info("Populating person_month.prior_benefit_transferred")

    # Prefetch related PersonMonth objects, ordered by month
    person_years = PersonYear.objects.filter(year__year=2025).prefetch_related(
        Prefetch(
            "personmonth_set",
            queryset=PersonMonth.objects.order_by("month"),
        )
    )
    total_person_years = person_years.count()

    with transaction.atomic():
        for counter, person_year in enumerate(person_years, start=1):
            logger.info(f"Processing person_year {counter}/{total_person_years}")

            prior_benefit_transferred = 0
            for person_month in person_year.personmonth_set.all():
                if prior_benefit_transferred:
                    person_month.prior_benefit_transferred = prior_benefit_transferred
                    person_month.save(update_fields=["prior_benefit_transferred"])

                prior_benefit_transferred += person_month.benefit_transferred or 0


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
