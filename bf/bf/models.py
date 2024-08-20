# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Sequence

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Index, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _
from eskat.models import ESkatMandtal
from simple_history.models import HistoricalRecords

from bf.data import engine_choices
from bf.exceptions import EstimationEngineUnset


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

    preferred_estimation_engine = models.CharField(
        max_length=100,
        choices=engine_choices,
        null=True,
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
        return self.name or self.cpr


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
    def amount_sum(self):
        return MonthlyIncomeReport.sum_queryset(
            MonthlyAIncomeReport.objects.filter(person_month__person_year=self)
        ) + MonthlyIncomeReport.sum_queryset(
            MonthlyBIncomeReport.objects.filter(person_month__person_year=self)
        )

    def calculate_benefit(self, estimated_year_income: Decimal) -> Decimal:
        if self.year.calculation_method is None:
            raise ReferenceError(
                f"Cannot calculate benefit; "
                f"calculation method not set for year {self.year}"
            )
        return self.year.calculation_method.calculate(estimated_year_income)

    @cached_property
    def prev(self):
        try:
            return self.person.personyear_set.get(year__year=self.year.year - 1)
        except PersonYear.DoesNotExist:
            return None

    @cached_property
    def next(self):
        try:
            return self.person.personyear_set.get(year__year=self.year.year + 1)
        except PersonYear.DoesNotExist:
            return None


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

    amount_sum = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal(0),
    )
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

    @cached_property
    def prev(self) -> PersonMonth | None:
        try:
            if self.month == 1:
                year: PersonYear = self.person_year.prev
                if year is not None:
                    return year.personmonth_set.get(month=12)
            else:
                return self.person_year.personmonth_set.get(month=self.month - 1)
        except PersonMonth.DoesNotExist:
            pass
        return None

    @cached_property
    def next(self) -> PersonMonth | None:
        try:
            if self.month == 12:
                year: PersonYear = self.person_year.next
                if year is not None:
                    return year.personmonth_set.get(month=1)
            else:
                return self.person_year.personmonth_set.get(month=self.month + 1)
        except PersonMonth.DoesNotExist:
            pass
        return None

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

    def update_amount_sum(self):
        self.amount_sum = MonthlyIncomeReport.sum_queryset(
            self.monthlyaincomereport_set
        ) + MonthlyIncomeReport.sum_queryset(self.monthlybincomereport_set)

    def __str__(self):
        return f"{self.person} ({self.year}/{self.month})"

    def calculate_benefit(self) -> Decimal:
        if not self.person.preferred_estimation_engine:
            raise EstimationEngineUnset(self.person)
        try:
            estimated_year_income = self.incomeestimate_set.get(
                engine=self.person.preferred_estimation_engine
            ).estimated_year_result
        except IncomeEstimate.DoesNotExist:  # pragma: nocover
            # TODO: preferred_estimation_engine skal ikke være fast for en person,
            # men defineres over en daterange, dvs. for en given range er en engine
            # preferred for en person.
            # Vi kommer hertil fordi en engine, f.eks. TwelveMonthSum, er preferred,
            # men der foreligger ikke nogen estimater fordi vi er i det første år
            # af personens indkomst
            return Decimal(0)

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

        if self.prev is not None:
            benefit_last_month = self.prev.benefit_paid
            threshold: Decimal = settings.CALCULATION_STICKY_THRESHOLD  # type: ignore
            if (
                benefit_last_month is not None
                and not benefit_this_month.is_zero()
                and not benefit_last_month.is_zero()
                and abs(benefit_last_month - benefit_this_month) / benefit_last_month
                < threshold
            ):
                benefit_this_month = benefit_last_month

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


class MonthlyIncomeReport(models.Model):
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.month = self.person_month.month
        self.year = self.person_month.year
        self.person = self.person_month.person

    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    @staticmethod
    def annotate_month(
        qs: QuerySet["MonthlyIncomeReport"],
    ) -> QuerySet["MonthlyIncomeReport"]:
        return qs.annotate(f_month=F("person_month__month"))

    @staticmethod
    def annotate_year(
        qs: QuerySet["MonthlyIncomeReport"],
    ) -> QuerySet["MonthlyIncomeReport"]:
        return qs.annotate(f_year=F("person_month__person_year__year"))

    @staticmethod
    def annotate_person_year(
        qs: QuerySet["MonthlyIncomeReport"],
    ) -> QuerySet["MonthlyIncomeReport"]:
        return qs.annotate(f_person_year=F("person_month__person_year"))

    @staticmethod
    def annotate_person(
        qs: QuerySet["MonthlyIncomeReport"],
    ) -> QuerySet["MonthlyIncomeReport"]:
        return qs.annotate(f_person=F("person_month__person_year__person"))

    @classmethod
    def sum_queryset(cls, qs: QuerySet["MonthlyIncomeReport"]):
        return qs.aggregate(sum=Coalesce(Sum("amount"), Decimal(0)))["sum"]

    @staticmethod
    def on_update_income_report(
        sender,
        instance: MonthlyIncomeReport,
        created: bool,
        raw: bool,
        using: str,
        update_fields: Sequence[str] | None,
        **kwargs,
    ):
        if update_fields is None or "amount" in update_fields:
            instance.person_month.update_amount_sum()


class MonthlyAIncomeReport(MonthlyIncomeReport):
    class Meta:
        indexes = (
            Index(
                name="MonthlyAIncomeReport_person",
                fields=("person_id",),
                include=(
                    "id",
                    "person",
                    "month",
                    "year",
                    "person_month",
                    "amount",
                    "employer",
                ),
            ),
            Index(
                name="MonthlyAIncomeReport_year",
                fields=("year",),
                include=("id", "person", "month", "person_month", "amount", "employer"),
            ),
            Index(
                name="MonthlyAIncomeReport_month",
                fields=("month",),
                include=("id", "person", "year", "person_month", "amount", "employer"),
            ),
        )

    employer = models.ForeignKey(Employer, on_delete=models.CASCADE)

    @property
    def person_year(self) -> PersonYear:
        return self.person_month.person_year

    def __str__(self):
        return f"{self.person_month} | {self.employer}"


post_save.connect(
    MonthlyIncomeReport.on_update_income_report,
    MonthlyAIncomeReport,
    dispatch_uid="MonthlyAIncomeReport_save",
)


class MonthlyBIncomeReport(MonthlyIncomeReport):
    class Meta:
        indexes = (
            Index(
                name="MonthlyBIncomeReport_person",
                fields=("person_id",),
                include=(
                    "id",
                    "person",
                    "month",
                    "year",
                    "person_month",
                    "amount",
                    "trader",
                ),
            ),
            Index(
                name="MonthlyBIncomeReport_year",
                fields=("year",),
                include=("id", "person", "month", "person_month", "amount", "trader"),
            ),
            Index(
                name="MonthlyBIncomeReport_month",
                fields=("month",),
                include=("id", "person", "year", "person_month", "amount", "trader"),
            ),
        )

    trader = models.ForeignKey(
        Employer,
        verbose_name=_("Indhandler"),
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.person_month} | {self.trader}"


post_save.connect(
    MonthlyIncomeReport.on_update_income_report,
    MonthlyBIncomeReport,
    dispatch_uid="MonthlyBIncomeReport_save",
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


class IncomeEstimate(models.Model):

    class Meta:
        unique_together = (("engine", "person_month"),)

    engine = models.CharField(max_length=100, choices=engine_choices)

    person_month = models.ForeignKey(
        PersonMonth, null=True, blank=True, on_delete=models.CASCADE
    )

    estimated_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    actual_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    @property
    def diff(self):
        # If we under-estimate diff is negative
        # If we over-estimate diff is positive
        return self.estimated_year_result - self.actual_year_result

    @property
    def absdiff(self):
        return abs(self.diff)

    @property
    def offset(self):
        return (
            (self.absdiff / self.actual_year_result) if self.actual_year_result else 0
        )

    @staticmethod
    def annotate_month(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_month=F("person_month__month"))

    @staticmethod
    def annotate_year(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_year=F("person_month__person_year__year"))

    @staticmethod
    def annotate_person_year(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_person_year=F("person_month__person_year"))

    def __str__(self):
        return f"{self.engine} ({self.person_month})"


class PersonYearEstimateSummary(models.Model):
    class Meta:
        unique_together = (("person_year", "estimation_engine"),)

    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    estimation_engine = models.CharField(
        max_length=100,
        null=False,
        blank=False,
    )
    mean_error_percent = models.DecimalField(
        max_digits=10, decimal_places=2, default=None, null=True
    )
    rmse_percent = models.DecimalField(
        max_digits=10, decimal_places=2, default=None, null=True
    )
