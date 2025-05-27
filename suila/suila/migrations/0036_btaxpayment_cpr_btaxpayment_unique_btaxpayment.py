from django.db import migrations, models

# Remove duplicate `BTaxPayment` objects (only those objects that have a `PersonMonth`
# FK can be processed, as those objects without do not have a unique CPR/date/amount)
REMOVE_OLD_DUPLICATES = """
    delete from suila_btaxpayment
        where
            person_month_id is not null
        and
            id not in (
                select
                    min(id)
                from
                    suila_btaxpayment
                where
                    person_month_id is not null
                group by
                    person_month_id,
                    rate_number,
                    date_charged,
                    amount_charged,
                    amount_paid
                having
                    count(*) > 1
                order by
                    person_month_id,
                    rate_number,
                    date_charged,
                    amount_charged,
                    amount_paid
            )
    ;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("suila", "0035_remove_historicalpersonmonth_paused_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=REMOVE_OLD_DUPLICATES),
        migrations.AddField(
            model_name="btaxpayment",
            name="cpr",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddConstraint(
            model_name="btaxpayment",
            constraint=models.UniqueConstraint(
                models.F("cpr"),
                models.F("amount_paid"),
                models.F("amount_charged"),
                models.F("date_charged"),
                models.F("rate_number"),
                name="unique_btaxpayment",
            ),
        ),
    ]
