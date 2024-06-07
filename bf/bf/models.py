from datetime import date

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from eskat.models import ESkatMandtal
from simple_history.models import HistoricalRecords


class Person(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    cpr = models.TextField(
        null=False,
        blank=False,
        max_length=10,
        validators=(RegexValidator(regex=r"\d{10}"),),
        verbose_name=_("CPR nummer"),
        help_text=_("CPR nummer"),
    )

    name = models.TextField(blank=True, null=True)
    address_line_1 = models.TextField(blank=True, null=True)
    address_line_2 = models.TextField(blank=True, null=True)
    address_line_3 = models.TextField(blank=True, null=True)
    address_line_4 = models.TextField(blank=True, null=True)
    address_line_5 = models.TextField(blank=True, null=True)
    full_address = models.TextField(blank=True, null=True)

    @classmethod
    def from_eskat_mandtal(cls, eskat_mandtal: ESkatMandtal) -> "Person":
        return Person(
            cpr=eskat_mandtal.cpr,
            name=eskat_mandtal.navn,
            address_line_1=eskat_mandtal.adresselinje1,
            address_line_2=eskat_mandtal.adresselinje2,
            address_line_3=eskat_mandtal.adresselinje3,
            address_line_4=eskat_mandtal.adresselinje4,
            address_line_5=eskat_mandtal.adresselinje5,
            full_address=eskat_mandtal.fuld_adresse,
        )


class PersonMonth(models.Model):
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
    )

    import_date = models.DateField(
        null=False,
        blank=False,
        verbose_name=_("Dato"),
    )

    municipality_code = models.IntegerField(blank=True, null=True)
    municipality_name = models.TextField(blank=True, null=True)
    fully_tax_liable = models.BooleanField(blank=True, null=True)

    @classmethod
    def from_eskat_mandtal(
        cls,
        eskat_mandtal: ESkatMandtal,
        person: Person,
        import_date: date,
    ) -> "PersonMonth":
        return PersonMonth(
            person=person,
            import_date=import_date,
            municipality_code=eskat_mandtal.kommune_no,
            municipality_name=eskat_mandtal.kommune,
            fully_tax_liable=eskat_mandtal.fully_tax_liable,
        )
