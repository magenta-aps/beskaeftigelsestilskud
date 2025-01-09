# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import List, Optional, Sequence, Tuple

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Index, QuerySet, Sum, TextChoices
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, pre_save
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from lxml import etree
from project.util import int_divide_end
from simple_history.models import HistoricalRecords

from bf.data import engine_choices
from bf.integrations.eboks.client import EboksClient, MessageFailureException
from bf.integrations.eskat.responses.data_models import TaxInformation


class IncomeType(TextChoices):
    A = "A"
    B = "B"
    U = "U"  # Udbytte / AKAP U1A


class ManagementCommands(TextChoices):
    CALCULATE_STABILITY_SCORE = "calculate_stability_score"
    AUTOSELECT_ESTIMATION_ENGINE = "autoselect_estimation_engine"
    LOAD_ESKAT = "load_eskat"
    ESTIMATE_INCOME = "estimate_income"
    CALCULATE_BENEFIT = "calculate_benefit"
    EXPORT_BENEFITS_TO_PRISME = "export_benefits_to_prisme"


class StatusChoices(TextChoices):
    RUNNING = "Kører"
    SUCCEEDED = "Gennemført"
    FAILED = "Fejl"


class WorkingTaxCreditCalculationMethod(models.Model):
    class Meta:
        abstract = True

    def calculate(self, year_income: Decimal) -> Decimal:
        raise NotImplementedError  # pragma: no cover

    @cached_property
    def graph_points(self) -> Sequence[Tuple[int | Decimal, int | Decimal]]:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    def subclass_instances(cls):
        return [
            item for subclass in cls.__subclasses__() for item in subclass.objects.all()
        ]

    @classmethod
    def subclasses_by_name(cls):
        return {subclass.__name__: subclass for subclass in cls.__subclasses__()}

    @property
    def years(self) -> QuerySet[Year]:
        return Year.objects.filter(
            calculation_method_content_type=ContentType.objects.get_for_model(
                self.__class__
            ),
            calculation_method_object_id=self.pk,
        )

    def __str__(self):
        name = self.__class__.__name__
        years = (
            ", ".join([str(year_object.year) for year_object in self.years])
            or "no years"
        )
        return f"{name} for {years}"


class StandardWorkBenefitCalculationMethod(WorkingTaxCreditCalculationMethod):

    benefit_rate_percent = models.DecimalField(
        verbose_name=_("Benefit rate percent"),
        max_digits=5,
        decimal_places=3,
        null=False,
        blank=False,
    )

    @cached_property
    def benefit_rate(self) -> Decimal:
        return self.benefit_rate_percent * Decimal("0.01")

    personal_allowance = models.DecimalField(
        verbose_name=_("Personal allowance"),
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    standard_allowance = models.DecimalField(
        verbose_name=_("Standard allowance"),
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    max_benefit = models.DecimalField(
        verbose_name=_("Max benefit"),
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    scaledown_rate_percent = models.DecimalField(
        verbose_name=_("Scaledown rate percent"),
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

    def calculate(self, year_income: Decimal) -> Decimal:
        zero = Decimal(0)
        rateable_amount = max(  # max A
            year_income - self.personal_allowance - self.standard_allowance, zero
        )
        scaledown_amount = max(year_income - self.scaledown_ceiling, zero)  # max B
        risen_benefit = min(  # min A
            self.benefit_rate * rateable_amount, self.max_benefit
        )
        return round(
            max(  # max C
                risen_benefit - self.scaledown_rate * scaledown_amount,
                zero,
            ),
            2,
        )

    # Identical to "calculate" but takes a float as an input
    def calculate_float(self, year_income: float) -> float:
        return float(self.calculate(Decimal(year_income)))

    @cached_property
    def graph_points(self) -> Sequence[Tuple[int | Decimal, int | Decimal]]:
        allowance = self.personal_allowance + self.standard_allowance
        # Calculate breakpoints in graph, by identifying points where the
        # contents of the min() and max() terms are identical,
        # then isolating year_income
        x_points: List[Decimal] = [Decimal(0)]

        # max A, where year_income == allowance
        x_points.append(allowance)

        # max B, where year_income == scaledown_ceiling
        x_points.append(self.scaledown_ceiling)

        # min A
        # (of max A, where year_income > allowance)
        #
        # max_benefit = benefit_rate * (year_income - allowance)
        # =>
        # max_benefit / benefit_rate = year_income - allowance
        # =>
        # max_benefit / benefit_rate + allowance = year_income
        if not self.benefit_rate_percent.is_zero():
            x_points.append((self.max_benefit / self.benefit_rate) + allowance)

        # min A
        # (of max A, where year_income < allowance)
        #
        # max_benefit = benefit_rate * 0
        # =>
        # year_income eliminated, no point here

        # max C
        # (of min A, where benefit_rate * rateable_amount < max_benefit),
        #     meaning risen_benefit = benefit_rate * rateable_amount
        # (of max B, where year_income > self.scaledown_ceiling,
        #     meaning scaledown_amount = year_income - scaledown_ceiling
        #
        # benefit_rate * (year_income - allowance)
        #     = scaledown_rate * (year_income - scaledown_ceiling)
        # =>
        # benefit_rate * year_income - benefit_rate * allowance
        #     = scaledown_rate * year_income - scaledown_rate * scaledown_ceiling
        # =>
        # benefit_rate * year_income - scaledown_rate * year_income
        #     = benefit_rate * allowance - scaledown_rate * scaledown_ceiling
        # =>
        # year_income * (benefit_rate - scaledown_rate)
        #     = benefit_rate * allowance - scaledown_rate * scaledown_ceiling
        # =>
        # year_income = (benefit_rate * allowance - scaledown_rate * scaledown_ceiling)
        #               / (benefit_rate - scaledown_rate)
        if self.benefit_rate_percent != self.scaledown_rate_percent:
            x_points.append(
                (
                    self.benefit_rate * allowance
                    - self.scaledown_rate * self.scaledown_ceiling
                )
                / (self.benefit_rate - self.scaledown_rate)
            )

        # max C
        # (of min A, where benefit_rate * rateable_amount < max_benefit),
        #     meaning risen_benefit = benefit_rate * rateable_amount
        # (of max B, where year_income < self.scaledown_ceiling,
        #     meaning scaledown_amount = 0
        #
        # benefit_rate * (year_income - allowance) = scaledown_rate * 0
        # =>
        # benefit_rate = 0 or year_income = allowance
        # Same as prior, no point added

        # max C
        # (of min A, where max_benefit < benefit_rate * rateable_amount),
        #     meaning risen_benefit = max_benefit
        # (of max B, where year_income > scaledown_ceiling,
        #     meaning scaledown_amount = year_income - scaledown_ceiling
        #
        # max_benefit = scaledown_rate * (year_income - scaledown_ceiling)
        # =>
        # max_benefit / scaledown_rate = year_income - scaledown_ceiling
        # =>
        # year_income = (max_benefit / scaledown_rate) + scaledown_ceiling
        if not self.scaledown_rate_percent.is_zero():
            x_points.append(
                (self.max_benefit / self.scaledown_rate) + self.scaledown_ceiling
            )

        # max C
        # (of min A, where benefit_rate * rateable_amount > max_benefit),
        #     meaning risen_benefit = max_benefit
        # (of max B, where year_income < scaledown_ceiling,
        #     meaning scaledown_amount = 0
        # max_benefit = scaledown_rate * 0
        # =>
        # year_income eliminated, no point here

        # dedup, filter out x<0, then sort ascending
        x_points = sorted(
            [Decimal(x).quantize(Decimal("0.01")) for x in set(x_points) if x >= 0]
        )

        # Calculate y for every x
        points = list(zip(x_points, [self.calculate(x) for x in x_points]))

        while len(points) > 1 and points[-1][1] == points[-2][1]:
            # Last two items have same y value, remove last point
            points.pop(-1)

        return points


class DataLoad(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20)
    parameters = models.JSONField(null=True)


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
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
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
    civil_state = models.TextField(blank=True, null=True)
    location_code = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.name or self.cpr)

    @property
    def last_year(self) -> PersonYear:
        return self.personyear_set.order_by("-year")[0]


class TaxScope(models.TextChoices):
    FULDT_SKATTEPLIGTIG = "FULD"
    DELVIST_SKATTEPLIGTIG = "DELVIS"
    FORSVUNDET_FRA_MANDTAL = "INGEN_MANDTAL"

    @classmethod
    def from_taxinformation(cls, taxinformation: TaxInformation) -> "TaxScope" | None:
        tax_scope_str = taxinformation.tax_scope
        if tax_scope_str == "FULL":
            return TaxScope.FULDT_SKATTEPLIGTIG
        if tax_scope_str == "LIM":
            return TaxScope.DELVIST_SKATTEPLIGTIG
        return None


class PersonYear(models.Model):

    class Meta:
        unique_together = (("person", "year"),)
        indexes = [
            models.Index(fields=("person", "year"))
            # index on "person" by itself is implicit because it's a ForeignKey
        ]

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )
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
    preferred_estimation_engine_a = models.CharField(
        max_length=100,
        choices=engine_choices,
        null=True,
        default="InYearExtrapolationEngine",
    )
    preferred_estimation_engine_b = models.CharField(
        max_length=100,
        choices=engine_choices,
        null=True,
        default="InYearExtrapolationEngine",
    )
    stability_score_a = models.DecimalField(
        decimal_places=1, default=None, null=True, max_digits=2
    )
    stability_score_b = models.DecimalField(
        decimal_places=1, default=None, null=True, max_digits=2
    )
    tax_scope = models.CharField(
        choices=TaxScope,
        default=TaxScope.FULDT_SKATTEPLIGTIG,
        max_length=20,
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.person} ({self.year})"

    @cached_property
    def quarantine_df(self):
        from common.utils import get_people_in_quarantine

        return get_people_in_quarantine(self.year.year, [self.person.cpr])

    @property
    def in_quarantine(self) -> bool:
        return self.quarantine_df.loc[self.person.cpr, "in_quarantine"]

    @property
    def quarantine_reason(self) -> bool:
        return self.quarantine_df.loc[self.person.cpr, "quarantine_reason"]

    @property
    def amount_sum(self) -> Decimal:
        return self.amount_sum_by_type(None)

    @cached_property
    def u1a_assessments_sum(self) -> Decimal:
        result = PersonYearU1AAssessment.objects.filter(person_year=self).aggregate(
            total=Sum("dividend_total")
        )["total"]

        return result or Decimal("0.00")

    def amount_sum_by_type(self, income_type: IncomeType | None) -> Decimal:
        sum = Decimal(0)
        if income_type in (IncomeType.A, None):
            sum += MonthlyIncomeReport.sum_queryset(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year=self, a_income__gt=0
                )
            )
        if income_type in (IncomeType.B, None):
            sum += MonthlyIncomeReport.sum_queryset(
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year=self, b_income__gt=0
                )
            )
            sum += self.b_income or 0
        return sum

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

    @property
    def b_income(self) -> Decimal | None:
        annual_income: AnnualIncome | None = self.annual_income_statements.order_by(
            "-created"
        ).first()

        return annual_income.account_tax_result if annual_income is not None else None

    @property
    def u_income(self) -> Decimal | None:
        u_income: Optional[Decimal] = None

        # Fetch AKAP u1a assessments sum
        if self.u1a_assessments_sum:
            if not u_income:
                u_income = Decimal("0.00")

            u_income += self.u1a_assessments_sum

        return u_income


class PersonMonth(models.Model):

    class Meta:
        indexes = [
            Index(fields=("month",)),
            Index(fields=("municipality_code",)),
        ]
        unique_together = ("person_year", "month")

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

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
    actual_year_benefit = models.DecimalField(
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
    estimated_year_result = models.DecimalField(
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

    def update_amount_sum(self):
        self.amount_sum = MonthlyIncomeReport.sum_queryset(self.monthlyincomereport_set)

    def __str__(self):
        return f"{self.person} ({self.year}/{self.month})"

    @property
    def year_month(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def b_income_from_year(self) -> int:
        b_income = self.person_year.b_income
        if b_income is not None:
            return int_divide_end(int(b_income), 12)[self.month - 1]
        return 0

    @property
    def u_income_from_year(self) -> int:
        u_income = self.person_year.u_income
        if u_income is not None:
            return int_divide_end(int(u_income), 12)[self.month - 1]
        return 0


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
    load = models.ForeignKey(DataLoad, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.name} ({self.cvr})"


class MonthlyIncomeReport(models.Model):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.month = self.person_month.month
        self.year = self.person_month.year
        self.person = self.person_month.person

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
    )

    employer = models.ForeignKey(
        Employer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Autoupdated fields. Do not write into these.
    a_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    b_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    # Source income fields. Write into these.
    salary_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    catchsale_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    public_assistance_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    alimony_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    dis_gis_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    retirement_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    disability_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    ignored_benefits_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    employer_paid_gl_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    foreign_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    civil_servant_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    other_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )
    capital_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
    )

    # TODO: More fields?

    @property
    def person_year(self) -> PersonYear:
        return self.person_month.person_year

    def update_amount(self):
        # Define how A and B income is calculated here.
        # TODO: Update as needed
        self.a_income = (
            self.salary_income
            + self.employer_paid_gl_pension_income
            + self.catchsale_income
        )
        self.b_income = self.disability_pension_income + self.capital_income

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

    def __str__(self):
        return f"Indkomst for {self.person_month}"

    @classmethod
    def sum_queryset(cls, qs: QuerySet["MonthlyIncomeReport"]):
        return qs.aggregate(
            sum=Coalesce(Sum(F("a_income") + F("b_income")), Decimal(0))
        )["sum"]

    @staticmethod
    def pre_save(sender, instance: MonthlyIncomeReport, *args, **kwargs):
        instance.update_amount()

    @staticmethod
    def post_save(
        sender,
        instance: MonthlyIncomeReport,
        created: bool,
        raw: bool,
        using: str,
        update_fields: Sequence[str] | None,
        **kwargs,
    ):
        if (
            update_fields is None
            or "a_income" in update_fields
            or "b_income" in update_fields
        ):
            instance.person_month.update_amount_sum()
            instance.person_month.save(update_fields=["amount_sum"])


pre_save.connect(
    MonthlyIncomeReport.pre_save,
    MonthlyIncomeReport,
    dispatch_uid="MonthlyIncomeReport_pre_save",
)

post_save.connect(
    MonthlyIncomeReport.post_save,
    MonthlyIncomeReport,
    dispatch_uid="MonthlyIncomeReport_post_save",
)


class BTaxPayment(models.Model):
    """This model is used for tracking whether the person has actually paid tax on their
    B income for a given month.
    They are only eligible for receiving benefits due to B income if they have indeed
    paid tax on their B income.
    Note that we only get a total amount of B tax paid - it is not split on the
    different types of B income.
    Also note that the B tax paid may differ from the B tax that was charged.
    """

    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    amount_charged = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    date_charged = models.DateField(
        null=False,
        blank=False,
    )

    rate_number = models.PositiveSmallIntegerField(
        null=False,
        blank=False,
    )

    filename = models.TextField(
        null=False,
        blank=False,
    )

    serial_number = models.PositiveBigIntegerField(
        null=False,
        blank=False,
    )

    def __str__(self) -> str:
        return f"{self.person_month}: {self.amount_paid}"


class IncomeEstimate(models.Model):

    class Meta:
        unique_together = (("engine", "person_month", "income_type"),)

    engine = models.CharField(max_length=100, choices=engine_choices)

    income_type = models.CharField(
        choices=IncomeType,
        default=IncomeType.A,
        max_length=1,
    )

    person_month = models.ForeignKey(
        PersonMonth, null=True, blank=True, on_delete=models.CASCADE
    )

    estimated_year_result = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=False,
        blank=False,
    )

    actual_year_result = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )

    timestamp = models.DateTimeField(
        null=True,
        blank=False,
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
        return (
            f"{self.engine} ({self.person_month}) ({IncomeType(self.income_type).name})"
        )

    @staticmethod
    def qs_offset(qs: QuerySet[IncomeEstimate]) -> Decimal:
        estimated_year_result = Decimal(0)
        actual_year_result = Decimal(0)
        for item in qs:
            estimated_year_result += item.estimated_year_result
            if item.actual_year_result:
                actual_year_result += item.actual_year_result
        absdiff = abs(estimated_year_result - actual_year_result)
        return (absdiff / actual_year_result) if actual_year_result else Decimal(0)


class PersonYearEstimateSummary(models.Model):
    class Meta:
        unique_together = (("person_year", "estimation_engine", "income_type"),)

    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    estimation_engine = models.CharField(
        max_length=100,
        null=False,
        blank=False,
    )
    income_type = models.CharField(
        choices=IncomeType,
        default=IncomeType.A,
        max_length=1,
    )
    mean_error_percent = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    rmse_percent = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    timestamp = models.DateTimeField(
        null=True,
        blank=False,
    )


class PersonYearAssessment(models.Model):
    # En forskudsopgørelse
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )
    person_year = models.ForeignKey(
        PersonYear, on_delete=models.CASCADE, related_name="assessments"
    )
    created = models.DateTimeField(
        auto_now_add=True,
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

    capital_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    education_support_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    care_fee_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    alimony_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    other_b_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    gross_business_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    brutto_b_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )


class PrismeAccountAlias(models.Model):
    class Meta:
        unique_together = [("tax_municipality_location_code", "tax_year")]

    alias = models.TextField(unique=True)
    """The account alias itself"""

    tax_municipality_location_code = models.TextField()
    """The 'stedkode' of the municipality issuing the benefit"""

    tax_year = models.PositiveSmallIntegerField()
    """The 'skatteår' in which the Prisme postings should be made"""

    def __str__(self):
        return f"{self.alias}"

    @property
    def tax_municipality_six_digit_code(self) -> str:
        return self.alias[-10:-4]


class PrismeBatch(models.Model):
    class Status(models.TextChoices):
        Sending = "sending", _("Sending")
        Sent = "sent", _("Sent")
        Failed = "failed", _("Failed")

    status = models.CharField(
        choices=Status.choices,
        default=Status.Sending,
        db_index=True,
    )

    failed_message = models.TextField()

    export_date = models.DateField(
        db_index=True,
    )

    prefix = models.IntegerField(
        db_index=True,
    )


class PrismeBatchItem(models.Model):
    class Meta:
        unique_together = ("prisme_batch", "person_month")

    class PostingStatus(models.TextChoices):
        Sent = "sent", _("Sent")
        Posted = "posted", _("Posted")
        Failed = "failed", _("Failed")

    prisme_batch = models.ForeignKey(
        PrismeBatch,
        on_delete=models.CASCADE,
    )

    person_month = models.OneToOneField(
        PersonMonth,
        on_delete=models.CASCADE,
    )

    g68_content = models.TextField()

    g69_content = models.TextField()

    posting_status_filename = models.TextField()
    """Contains the filename of the the "bogføringsstatus" (posting status) CSV file"""

    invoice_no = models.TextField(
        null=True,
        unique=True,
    )
    """Contains the invoice number used for this Prisme batch item"""

    status = models.CharField(
        choices=PostingStatus.choices,
        default=PostingStatus.Sent,
        db_index=True,
    )
    """Indicates posting status (bogføringsstatus) in Prisme.
    - `Sent`:   the item has been sent to Prisme, but we don't know its posting
                status yet.
    - `Posted`: the item is assumed to have been posted (bogført) in Prisme.
                This happens when processing an item whose due date is in the past,
                *and* is not present on the list of failed postings.
    - `Failed`: the item is present on the list of failed postings.
    """

    error_code = models.TextField()
    """Contains an error code received from NemKonto when the item was attempted to be
    posted in Prisme. Only valid if `PrismeBatchItem.status` is `PostingStatus.Failed`.
    """

    error_description = models.TextField()
    """Contains an error description received from NemKonto when the item was attempted
    to be posted in Prisme. Only valid if `PrismeBatchItem.status` is
    `PostingStatus.Failed`.
    """


class AnnualIncome(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
    )
    person_year = models.ForeignKey(
        PersonYear, on_delete=models.CASCADE, related_name="annual_income_statements"
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )
    created = models.DateTimeField(
        auto_now_add=True,
    )
    salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    public_assistance_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    retirement_pension_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    disability_pension_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    ignored_benefits = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    occupational_benefit = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    foreign_pension_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    subsidy_foreign_pension_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    dis_gis_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    other_a_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    deposit_interest_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    bond_interest_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    other_interest_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    education_support_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    care_fee_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    alimony_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    foreign_dividend_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    foreign_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_journey_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    group_life_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    rental_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    other_b_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_board_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_lodging_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_housing_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_phone_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_car_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_internet_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_boat_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    free_other_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    pension_payment_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    catch_sale_market_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    catch_sale_factory_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_tax_result = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_share_business_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    shareholder_dividend_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )


class JobLog(models.Model):
    """
    model which keeps track of:
        - which jobs were run
        - On what date
        - Whether they finished
        - With which args/kwargs
    """

    name = models.TextField(choices=ManagementCommands)
    runtime = models.DateTimeField(auto_now_add=True)
    year = models.IntegerField(default=None, null=True)
    month = models.IntegerField(default=None, null=True)
    status = models.TextField(default=StatusChoices.RUNNING, choices=StatusChoices)

    # Job parameters
    year_param = models.IntegerField(default=None, null=True)
    month_param = models.IntegerField(default=None, null=True)
    count_param = models.IntegerField(default=None, null=True)
    cpr_param = models.TextField(default=None, null=True)
    type_param = models.TextField(default=None, null=True)
    verbosity_param = models.IntegerField(default=None, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.year = self.runtime.year
        self.month = self.runtime.month
        super().save(update_fields=["year", "month"])


class EboksMessage(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    sent = models.DateTimeField(null=True)
    xml = models.BinaryField()
    cpr_cvr = models.CharField(validators=[RegexValidator(r"\d{8,10}")])
    title = models.CharField(max_length=255)
    content_type = models.IntegerField()
    message_id = models.CharField(max_length=255)
    status = models.CharField(
        choices=(
            ("created", _("Genereret")),
            # sent means that the message was successfully delivered to e-boks.
            ("sent", _("Afsendt")),
            # Successfully sent to proxy but awaiting post-processing
            ("post_processing", _("Afventer efterbehandling")),
            # Could not deliver message.
            ("failed", _("Afsendelse fejlet")),
        ),
        max_length=20,
    )
    recipient_status = models.CharField(
        choices=(
            ("", _("Gyldig E-boks modtager")),
            ("exempt", _("Fritaget modtager")),
            ("invalid", _("Ugyldig E-boks modtager (sendes til efterbehandling)")),
            ("dead", _("Afdød")),
            ("minor", _("Mindreårig")),
        ),
        max_length=8,
    )
    post_processing_status = models.CharField(
        choices=(
            ("", ""),
            ("pending", _("Afventer processering")),
            ("address resolved", _("Fundet gyldig postadresse")),
            ("address not found", _("Ingen gyldig postadresse")),
            ("remote printed", _("Overført til fjernprint")),
        ),
        default="",
        blank=True,
        max_length=20,
    )
    is_postprocessing = models.BooleanField(
        default=False,
        db_index=True,
    )

    @classmethod
    def dispatch(
        cls, cpr_cvr: str, title: str, content_type: int, pdf_data: bytes
    ) -> EboksMessage:
        message = cls(cpr_cvr=cpr_cvr, title=title, content_type=content_type)
        message.set_pdf_data(pdf_data)
        message.send()
        return message

    def set_pdf_data(self, pdf_data: bytes):
        self.xml = self.generate_xml(
            self.cpr_cvr, self.title, self.content_type, pdf_data
        )

    def send(self, client: EboksClient | None = None) -> None:
        self.sent = timezone.now()
        created_client = False
        if not self.pk:
            self.save()
        if client is None:
            client = EboksClient.from_settings()
            created_client = True
        try:
            message_id = client.get_message_id()
            self.message_id = message_id
            response = client.send_message(self, message_id, 5)
            response_json = response.json()
        except MessageFailureException as e:
            self.status = "failed"
            self.message_id = e.message_id
            self.save(update_fields=["status", "message_id", "sent"])
            raise
        else:
            self.message_id = response_json[
                "message_id"
            ]  # message_id might have changed so get it from the response
            # we always only have 1 recipient
            recipient = response_json["recipients"][0]
            self.recipient_status = recipient["status"]
            self.sent = timezone.now()
            if recipient["post_processing_status"] == "":
                self.status = "sent"
                self.is_postprocessing = False

            else:
                self.status = "post_processing"
                self.is_postprocessing = True
            self.save(
                update_fields=["status", "message_id", "sent", "is_postprocessing"]
            )
        finally:
            if created_client:
                client.close()

    @staticmethod
    def generate_xml(
        cpr_cvr: str, title: str, content_type_id: int, pdf_data: bytes
    ) -> bytes:
        if not cpr_cvr.isdigit():
            raise ValueError("cpr/cvr must be all digits")
        root = etree.Element("Dispatch", xmlns="urn:eboks:en:3.0.0")
        recipient = etree.Element("DispatchRecipient")
        recipient_id = etree.Element("Id")
        recipient_id.text = cpr_cvr
        recipient.append(recipient_id)
        r_type = etree.Element("Type")
        if len(cpr_cvr) == 10:
            r_type.text = "P"
        elif len(cpr_cvr) == 8:
            r_type.text = "V"
        else:
            raise ValueError(f"unknown recipient type for: {cpr_cvr}")
        recipient.append(r_type)
        nationality = etree.Element("Nationality")
        nationality.text = "DK"
        recipient.append(nationality)
        root.append(recipient)

        content_type = etree.Element("ContentTypeId")
        content_type.text = str(content_type_id)
        root.append(content_type)

        title_elemt = etree.Element("Title")
        title_elemt.text = title
        root.append(title_elemt)

        content = etree.Element("Content")
        data = etree.Element("Data")
        data.text = base64.b64encode(pdf_data).decode("utf-8")
        content.append(data)
        file_extension = etree.Element("FileExtension")
        file_extension.text = "pdf"
        content.append(file_extension)
        root.append(content)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    @staticmethod
    def update_final_statuses(client: EboksClient | None = None):
        if EboksMessage.objects.filter(is_postprocessing=True).exists():
            if client is None:
                client = EboksClient.from_settings()
            qs = EboksMessage.objects.filter(is_postprocessing=True)
            messages = {message.message_id: message for message in qs}
            response = client.get_recipient_status(list(messages.keys()))
            for response_message in response.json():
                message_id = response_message["message_id"]
                message = messages[message_id]
                recipient = response_message["recipients"][0]
                if recipient["post_processing_status"] != "pending":
                    message.status = "sent"
                    message.post_processing_status = recipient["post_processing_status"]
                    message.is_postprocessing = False
                    message.save(
                        update_fields=[
                            "status",
                            "post_processing_status",
                            "is_postprocessing",
                        ]
                    )


# U1A Import


class PersonYearU1AAssessment(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    person_year = models.ForeignKey(
        PersonYear, on_delete=models.CASCADE, related_name="u1a_assessments"
    )

    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

    u1a_ids = models.CharField(
        verbose_name=_("U1A IDs i AKAP"),
        max_length=255,
        error_messages={"required": "error.required", "invalid": "error.invalid_email"},
    )

    dividend_total = models.DecimalField(
        verbose_name=_("Udbetalt/godskrevet udbytte i DKK, før skat"),
        max_digits=12,
        decimal_places=2,
        error_messages={
            "required": "error.required",
            "invalid": "error.number_required",
        },
    )

    created = models.DateTimeField(
        auto_now_add=True,
    )
