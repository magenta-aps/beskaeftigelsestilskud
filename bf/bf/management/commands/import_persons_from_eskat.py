from datetime import datetime

from django.core.management.base import BaseCommand
from eskat.models import ESkatMandtal

from bf.models import PersonMonth


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(  # pragma: nocover
            "import_date",
            type=str,
            help="Import date (format: YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        # Parse mandatory `import_date` command line option
        import_date = datetime.strptime(
            options["import_date"],
            "%Y-%m-%d",
        )
        # Convert to date and force to 1st of month
        import_date = import_date.date().replace(day=1)

        # Load mandtal from external database
        eskat_mandtal_objects = ESkatMandtal.objects.all()

        # Create or update objects for this month
        person_months = [
            PersonMonth.from_eskat_mandtal(eskat_mandtal, import_date)
            for eskat_mandtal in eskat_mandtal_objects
        ]
        PersonMonth.objects.bulk_create(
            person_months,
            update_conflicts=True,
            unique_fields=["cpr", "import_date"],
            update_fields=[
                "name",
                "municipality_code",
                "municipality_name",
                "address_line_1",
                "address_line_2",
                "address_line_3",
                "address_line_4",
                "address_line_5",
                "full_address",
                "fully_tax_liable",
            ],
        )
