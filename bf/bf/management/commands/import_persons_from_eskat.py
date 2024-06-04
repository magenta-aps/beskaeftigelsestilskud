from datetime import date

from django.core.management.base import BaseCommand

from bf.models import PersonMonth
from eskat.models import ESkatMandtal


class Command(BaseCommand):
    def handle(self, *args, **options):
        import_date = date.today().replace(day=1)
        person_months = [
            PersonMonth.from_eskat_mandtal(eskat_mandtal, import_date)
            for eskat_mandtal in ESkatMandtal.objects.all()
        ]
        PersonMonth.objects.bulk_create(person_months)
