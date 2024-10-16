# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass
from datetime import date
from typing import TypeAlias

from django.core.management.base import BaseCommand
from django.db import transaction
from eskat.models import ESkatMandtal
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from bf.models import Person, PersonMonth

CPR: TypeAlias = str


@dataclass(frozen=True, slots=True)
class MandtalResult:
    mandtal_by_cpr: dict[CPR, ESkatMandtal]
    new_mandtal_objects: list[ESkatMandtal]
    year: int  # The year that was queried from the database
    import_date: date  # The date we got data from the database

    @property
    def month(self) -> int:
        if self.year == self.import_date.year:
            # We import part of a year
            return self.import_date.month
        else:
            # We import a prior, completed year
            return 12


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("year", type=int, help="Import year")

    def handle(self, *args, **options):
        # Convert to date and force to 1st of month
        year = options["year"]

        # Load mandtal data from external eSkat database
        mandtal_result: MandtalResult = self._get_mandtal(year)

        # Create and update objects in application database
        with transaction.atomic():
            # Create `Person` objects for new mandtal objects
            persons_created = self._create_persons(mandtal_result)
            # Update `Person` objects for mandtal objects we already know
            persons_updated = self._update_persons(mandtal_result)
            # Create or update `PersonMonth` objects for total set of mandtal objects
            # (new and updated.)
            person_months_created, person_months_updated = (
                self._create_or_update_person_months(
                    mandtal_result,
                    persons_created + persons_updated,
                )
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(persons_created)} new persons, "
                    f"updated {len(persons_updated)} persons, "
                    f"created {len(person_months_created)} new person months, and "
                    f"updated {len(person_months_updated)} person months."
                )
            )

    def _get_mandtal(self, year: int) -> MandtalResult:
        # Create map of (mandtal CPR, mandtal object) for a given year
        mandtal_by_cpr = {m.cpr: m for m in ESkatMandtal.objects.filter(skatteaar=year)}
        # Find any new CPRs in mandtal by comparing to current set of
        # `Person` CPRs.
        mandtal_cprs = set(mandtal_by_cpr.keys())
        local_cprs = set(Person.objects.values_list("cpr", flat=True))
        new_mandtal_objects = [
            mandtal_by_cpr[cpr] for cpr in (mandtal_cprs - local_cprs)
        ]
        return MandtalResult(
            mandtal_by_cpr=mandtal_by_cpr,
            new_mandtal_objects=new_mandtal_objects,
            year=year,
            import_date=date.today(),
        )

    def _create_persons(
        self,
        mandtal_result: MandtalResult,
    ) -> list[Person]:
        persons_to_create = [
            Person.from_eskat_mandtal(eskat_mandtal)
            for eskat_mandtal in mandtal_result.new_mandtal_objects
        ]
        bulk_create_with_history(
            persons_to_create,
            Person,
            default_date=mandtal_result.import_date,
        )
        return persons_to_create

    def _update_persons(
        self,
        mandtal_result: MandtalResult,
    ) -> list[Person]:
        # Update `Person` objects whose CPR are in `mandtal_by_cpr` but not in
        # `new_mandtal_objects`.
        persons_to_update = Person.objects.filter(
            cpr__in=set(mandtal_result.mandtal_by_cpr.keys())
        ).exclude(cpr__in={m.cpr for m in mandtal_result.new_mandtal_objects})

        # Do the actual updates (without saving the objects)
        for p in persons_to_update:
            m = mandtal_result.mandtal_by_cpr[p.cpr]
            p.name = m.navn
            p.address_line_1 = m.adresselinje1
            p.address_line_2 = m.adresselinje2
            p.address_line_3 = m.adresselinje3
            p.address_line_4 = m.adresselinje4
            p.address_line_5 = m.adresselinje5
            p.full_address = m.fuld_adresse

        # Save the objects (and their history)
        bulk_update_with_history(
            persons_to_update,
            Person,
            [
                "name",
                "address_line_1",
                "address_line_2",
                "address_line_3",
                "address_line_4",
                "address_line_5",
                "full_address",
            ],
            default_date=mandtal_result.import_date,
        )
        return list(persons_to_update)

    def _create_or_update_person_months(
        self,
        mandtal_result: MandtalResult,
        persons: list[Person],
    ) -> tuple[list[PersonMonth], list[PersonMonth]]:
        # Build list of `PersonMonth` objects to create, and `PersonMonth` objects
        # to update (in case there is already data for the same CPRs on the same import
        # date.)
        current_person_months = PersonMonth.objects.filter(
            person_year__year_id=mandtal_result.year, month=mandtal_result.month
        )
        persons_by_cpr = {p.cpr: p for p in persons}
        person_months = [
            PersonMonth.from_eskat_mandtal(
                mandtal,
                persons_by_cpr[mandtal_cpr],
                mandtal_result.import_date,
                mandtal_result.year,
                mandtal_result.month,
            )
            for mandtal_cpr, mandtal in mandtal_result.mandtal_by_cpr.items()
        ]

        # Create `PersonMonth` objects for data we haven't seen yet.
        person_months_to_create = [
            person_month
            for person_month in person_months
            if person_month.person.cpr
            not in current_person_months.values_list(
                "person_year__person__cpr", flat=True
            )
        ]
        PersonMonth.objects.bulk_create(person_months_to_create)

        # Update `PersonMonth` objects for the remaining data which we have already
        # seen once.
        person_months_to_update = list(
            current_person_months.exclude(
                person_year__person__cpr__in={
                    person_month.person.cpr for person_month in person_months_to_create
                }
            )
        )
        for person_month in person_months_to_update:
            mandtal = mandtal_result.mandtal_by_cpr[person_month.person.cpr]
            person_month.municipality_code = mandtal.kommune_no
            person_month.municipality_name = mandtal.kommune
            person_month.fully_tax_liable = mandtal.fully_tax_liable

        PersonMonth.objects.bulk_update(
            person_months_to_update,
            ["municipality_code", "municipality_name", "fully_tax_liable"],
        )

        return person_months_to_create, person_months_to_update
