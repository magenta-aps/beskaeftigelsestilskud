from decimal import Decimal

from django.db import migrations
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce


def _update_amount_sums(apps, person_month_ids):
    """Recalculate `PersonMonth.amount_sum` for the given person months, using the
    same definition as `MonthlyIncomeReport.sum_queryset`.
    """
    MonthlyIncomeReport = apps.get_model("suila", "MonthlyIncomeReport")
    PersonMonth = apps.get_model("suila", "PersonMonth")

    amount_sum = (
        MonthlyIncomeReport.objects.filter(person_month=OuterRef("pk"))
        .order_by()
        .values("person_month")
        .annotate(total=Sum(F("a_income") + F("u_income")))
        .values("total")
    )
    PersonMonth.objects.filter(pk__in=person_month_ids).update(
        amount_sum=Coalesce(
            Subquery(amount_sum),
            Value(Decimal(0)),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )


def _recalculate(apps, include_foreign_pension: bool):
    MonthlyIncomeReport = apps.get_model("suila", "MonthlyIncomeReport")

    reports = MonthlyIncomeReport.objects.filter(foreign_pension_income__gt=0)
    person_month_ids = list(
        reports.values_list("person_month_id", flat=True).distinct()
    )

    a_income = (
        F("salary_income")
        + F("employer_paid_gl_pension_income")
        + F("catchsale_income")
    )
    if include_foreign_pension:
        a_income = a_income + F("foreign_pension_income")
    reports.update(a_income=a_income)

    _update_amount_sums(apps, person_month_ids)


def add_foreign_pension_to_a_income(apps, schema_editor):
    """Foreign pension is now part of the A income used by the estimation engines, but
    existing income reports were saved before that change. Recalculate them, so the
    already imported foreign pension is included in the next estimation.
    """
    _recalculate(apps, include_foreign_pension=True)


def remove_foreign_pension_from_a_income(apps, schema_editor):
    _recalculate(apps, include_foreign_pension=False)


class Migration(migrations.Migration):

    dependencies = [
        ("suila", "0068_suilaeboksmessage_person_year_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_foreign_pension_to_a_income, # Runs when migrating 0068 - 0069
            remove_foreign_pension_from_a_income, # Runs when rolling back
        ),
    ]
