# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Dict

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Index, Sum
from django.utils.translation import gettext_lazy as _
from eskat.models import ESkatMandtal
from simple_history.models import HistoricalRecords


class WorkingTaxCreditCalculationMethod(models.Model):
    class Meta:
        abstract = True

    def calculate(self, amount: Decimal) -> Decimal:
        raise NotImplementedError  # pragma: no cover


class StandardWorkBenefitCalculationMethod(WorkingTaxCreditCalculationMethod):

    benefit_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        null=False,
        blank=False,
    )

    @cached_property
    def benefit_rate(self) -> Decimal:
        return self.benefit_rate_percent * Decimal("0.01")

    personal_allowance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    standard_allowance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    max_benefit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    scaledown_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        null=False,
        blank=False,
    )

    @cached_property
    def scaledown_rate(self) -> Decimal:
        return self.scaledown_rate_percent * Decimal("0.01")

    scaledown_ceiling = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    def calculate(self, amount: Decimal) -> Decimal:
        zero = Decimal(0)
        rateable_amount = max(
            amount - self.personal_allowance - self.standard_allowance, zero
        )
        scaledown_amount = max(amount - self.scaledown_ceiling, zero)
        return round(
            max(
                min(self.benefit_rate * rateable_amount, self.max_benefit)
                - self.scaledown_rate * scaledown_amount,
                zero,
            ),
            2,
        )


class Year(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    calculation_method_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    calculation_method_object_id = models.PositiveIntegerField(null=True, blank=True)
    calculation_method = GenericForeignKey(
        "calculation_method_content_type", "calculation_method_object_id"
    )

    def __str__(self):
        return str(self.year)


class Person(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    cpr = models.TextField(
        null=False,
        blank=False,
        unique=True,
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

    preferred_prediction_engine = models.CharField(
        max_length=100,
        choices=(
            # We could create this list with [
            #     (cls.__name__, cls.description)
            #     for cls in CalculationEngine.__subclasses__()
            # ]
            # but that would make a circular import
            (
                "InYearExtrapolationEngine",
                "Ekstrapolation af beløb for måneder i indeværende år",
            ),
            (
                "TwelveMonthsSummationEngine",
                "Summation af beløb for de seneste 12 måneder",
            ),
        ),
    )

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
        blank=False,
        null=False,
    )
    year = models.ForeignKey(
        Year,
        on_delete=models.CASCADE,
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
            AIncomeReport.objects.filter(person_month__person_year=self)
            .annotate(
                f_year=F("person_month__person_year__year_id"),
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

    def calculate_benefit(self, estimated_year_income: Decimal) -> Decimal:
        if self.year.calculation_method is None:
            raise ReferenceError(
                f"Cannot calculate benefit; "
                f"calculation method not set for year {self.year}"
            )
        return self.year.calculation_method.calculate(estimated_year_income)


class PersonMonth(models.Model):

    class Meta:
        indexes = [
            Index(fields=("month",)),
            Index(fields=("municipality_code",)),
        ]
        unique_together = ("person_year", "month")

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

    benefit_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    estimated_year_benefit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    prior_benefit_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    @property
    def person(self):
        return self.person_year.person

    @property
    def year(self):
        return self.person_year.year_id

    @classmethod
    def from_eskat_mandtal(
        cls,
        eskat_mandtal: ESkatMandtal,
        person: Person,
        import_date: date,
        year: int,
        month: int,
    ) -> "PersonMonth":
        year_obj, _ = Year.objects.get_or_create(year=year)
        person_year, _ = PersonYear.objects.get_or_create(person=person, year=year_obj)
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
        estimated_year_income: Decimal = Decimal(0)
        for salary_report in self.aincomereport_set.all():
            # Using a list comp. in a sum() makes MyPy complain
            estimated_year_income += salary_report.calculated_year_result or 0
        # TODO: medtag andre relevante indkomster i summen

        # Foretag en beregning af beskæftigelsestilskud for hele året
        self.estimated_year_benefit = self.person_year.calculate_benefit(
            estimated_year_income
        )

        # Tidligere måneder i året for denne person
        prior_months = self.person_year.personmonth_set.filter(month__lt=self.month)
        # Totalt beløb der allerede er udbetalt tidligere på året
        self.prior_benefit_paid = (
            prior_months.aggregate(sum=Sum("benefit_paid"))["sum"] or 0
        )
        assert self.prior_benefit_paid is not None  # To shut MyPy up

        # Denne måneds udbetaling =
        # manglende udbetaling for resten af året (inkl. denne måned)
        # divideret med antal måneder vi udbetaler dette beløb over (inkl. denne måned)
        benefit_this_month = round(
            (self.estimated_year_benefit - self.prior_benefit_paid) / (13 - self.month),
            2,
        )

        # Hvis vi har udbetalt for meget før, og denne måned er negativ,
        # lad være med at udbetale noget
        if benefit_this_month < 0:
            benefit_this_month = Decimal(0)

        self.benefit_paid = benefit_this_month

        return benefit_this_month


class Employer(models.Model):
    cvr = models.PositiveIntegerField(
        verbose_name=_("CVR-nummer"),
        db_index=True,
        unique=True,
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


class AIncomeReport(models.Model):

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
        return self.person_month.person_year.year_id

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


class MonthlyBIncomeReport(models.Model):
    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
    )
    trader = models.ForeignKey(
        Employer,
        verbose_name=_("Indhandler"),
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )


class SelfAssessedYearlyBIncome(models.Model):
    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    reported_date = models.DateTimeField(
        auto_now_add=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )


class FinalBIncomeReport(models.Model):
    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    reported_date = models.DateTimeField(
        auto_now_add=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
