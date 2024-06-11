from datetime import date

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
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


class PersonYear(models.Model):
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
    )
    year = models.PositiveSmallIntegerField(
        blank=False,
        null=False,
    )

    class Meta:
        unique_together = (("person", "year"),)
        indexes = [
            models.Index(fields=("person", "year"))
            # index on "person" by itself is implicit because it's a ForeignKey
        ]


class PersonMonth(models.Model):

    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    import_date = models.DateField(
        null=False,
        blank=False,
        verbose_name=_("Dato"),
    )

    municipality_code = models.IntegerField(blank=True, null=True)
    municipality_name = models.TextField(blank=True, null=True)
    fully_tax_liable = models.BooleanField(blank=True, null=True)
    month = models.PositiveSmallIntegerField(blank=False, null=False)

    @property
    def person(self):
        return self.person_year.person

    @property
    def year(self):
        return self.person_year.year

    @classmethod
    def from_eskat_mandtal(
        cls,
        eskat_mandtal: ESkatMandtal,
        person: Person,
        import_date: date,
        year: int,
        month: int,
    ) -> "PersonMonth":
        person_year, _ = PersonYear.objects.get_or_create(person=person, year=year)
        return PersonMonth(
            person_year=person_year,
            month=month,
            import_date=import_date,
            municipality_code=eskat_mandtal.kommune_no,
            municipality_name=eskat_mandtal.kommune,
            fully_tax_liable=eskat_mandtal.fully_tax_liable,
        )


class Employer(models.Model):
    cvr = models.PositiveIntegerField(
        verbose_name=_("CVR-nummer"),
        db_index=True,
        validators=(
            MinValueValidator(1000000),
            MaxValueValidator(99999999),
        ),
        null=False,
        blank=False,
    )
    name = models.CharField(
        null=True,
        blank=True,
    )


class ASalaryReport(models.Model):

    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
    )
    employer = models.ForeignKey(Employer, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    @property
    def year(self):
        return self.person_month.person_year.year

    @property
    def month(self):
        return self.person_month.month
