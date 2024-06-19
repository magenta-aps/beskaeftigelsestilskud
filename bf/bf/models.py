# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal
from typing import Dict

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Index, Sum
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

    def __str__(self):
        return self.name


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

    def __str__(self):
        return f"{self.person} ({self.year})"

    @property
    def salary_reports(self):
        return (
            ASalaryReport.objects.filter(person_month__person_year=self)
            .annotate(
                f_year=F("person_month__person_year__year"),
                f_month=F("person_month__month"),
            )
            .order_by("f_year", "f_month", "employer")
        )

    @property
    def latest_calculation_by_employer(self) -> Dict["Employer", Decimal]:
        """
        Extracts the lastest year-estimates from reports for each employer
        :return:
        """
        latest_by_employer = {}
        for report in self.salary_reports.reverse():
            if report.employer not in latest_by_employer:
                latest_by_employer[report.employer] = report.calculated_year_result
        return latest_by_employer

    @property
    def latest_calculation(self) -> Decimal:
        """
        Returns the total lastest year-estimates from reports
        :return:
        """
        return sum(self.latest_calculation_by_employer.values())  # type: ignore

    @staticmethod
    def calculate_benefit(estimated_year_income: Decimal) -> Decimal:
        # TODO
        raise NotImplementedError  # pragma: no cover


class PersonMonth(models.Model):

    class Meta:
        indexes = [
            Index(fields=("month",)),
            Index(fields=("municipality_code",)),
        ]

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

    paid_out = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

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

    def __str__(self):
        return f"{self.person} ({self.year}/{self.month})"

    def calculate_benefit(self) -> Decimal:
        estimated_year_income: Decimal = sum(  # type: ignore
            [
                salary_report.calculated_year_result or 0
                for salary_report in self.asalaryreport_set.all()
            ]
        )

        # Foretag en beregning af beskæftigelsestilskud for hele året
        year_benefit = PersonYear.calculate_benefit(estimated_year_income)

        # Tidligere måneder i året for denne person
        prior_months = self.person_year.personmonth_set.filter(month__lt=self.month)
        # Totalt beløb der allerede er udbetalt tidligere på året
        already_paid_out = prior_months.aggregate(sum=Sum("paid_out"))["sum"] or 0

        # Denne måneds udbetaling =
        # manglende udbetaling for resten af året (inkl. denne måned)
        # divideret med antal måneder vi udbetaler dette beløb over (inkl. denne måned)
        benefit_this_month = (year_benefit - already_paid_out) / (13 - self.month)

        # TODO: Gem mellemregninger så vi kan vise dem til borgeren
        return benefit_this_month


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

    def __str__(self):
        return f"{self.name} ({self.cvr})"


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
    def month(self) -> int:
        return self.person_month.month

    @property
    def person_year(self) -> PersonYear:
        return self.person_month.person_year

    @property
    def year(self) -> int:
        return self.person_month.person_year.year

    @property
    def person(self) -> Person:
        return self.person_month.person_year.person

    @property
    def calculated_year_result(self) -> Decimal | None:
        first_item = self.calculationresult_set.first()
        if first_item is None:
            return None
        return first_item.calculated_year_result

    def __str__(self):
        return f"{self.person_month} | {self.employer}"
