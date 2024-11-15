# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Sequence, Tuple

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Index, QuerySet, Sum, TextChoices
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, pre_save
from django.utils.translation import gettext_lazy as _
from project.util import int_divide_end
from simple_history.models import HistoricalRecords

from bf.data import engine_choices
from bf.integrations.eskat.responses.data_models import TaxInformation


class IncomeType(TextChoices):
    A = "A"
    B = "B"


class WorkingTaxCreditCalculationMethod(models.Model):
    class Meta:
        abstract = True

    def calculate(self, year_income: Decimal) -> Decimal:
        raise NotImplementedError  # pragma: no cover

    @cached_property
    def graph_points(self) -> Sequence[Tuple[int | Decimal, int | Decimal]]:
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

    def calculate(self, year_income: Decimal) -> Decimal:
        zero = Decimal(0)
        rateable_amount = max(
            year_income - self.personal_allowance - self.standard_allowance, zero
        )
        scaledown_amount = max(year_income - self.scaledown_ceiling, zero)
        return round(
            max(
                min(self.benefit_rate * rateable_amount, self.max_benefit)
                - self.scaledown_rate * scaledown_amount,
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
        return [
            (Decimal(0), Decimal(0)),
            (allowance, Decimal(0)),
            ((allowance + self.max_benefit / self.benefit_rate), self.max_benefit),
            (self.scaledown_ceiling, self.max_benefit),
            (
                self.max_benefit / self.scaledown_rate + self.scaledown_ceiling,
                Decimal(0),
            ),
        ]


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
    def from_taxinformation(cls, taxinformation: TaxInformation) -> "TaxScope":
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

    def amount_sum_by_type(self, income_type: IncomeType | None) -> Decimal:
        sum = Decimal(0)
        if income_type in (IncomeType.A, None):
            sum += MonthlyIncomeReport.sum_queryset(
                MonthlyAIncomeReport.objects.filter(person_month__person_year=self)
            )
        if income_type in (IncomeType.B, None):
            sum += MonthlyIncomeReport.sum_queryset(
                MonthlyBIncomeReport.objects.filter(person_month__person_year=self)
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
        final_settlement: FinalSettlement | None = self.final_settlements.order_by(
            "-created"
        ).first()
        if final_settlement is not None:
            return final_settlement.skattemæssigt_resultat
        return None


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
        self.amount_sum = MonthlyIncomeReport.sum_queryset(
            self.monthlyaincomereport_set
        ) + MonthlyIncomeReport.sum_queryset(self.monthlybincomereport_set)

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
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.month = self.person_month.month
        self.year = self.person_month.year
        self.person = self.person_month.person

    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )
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

    def update_amount(self):
        self.amount = (
            self.salary_income
            + self.employer_paid_gl_pension_income
            + self.catchsale_income
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
        if update_fields is None or "amount" in update_fields:
            instance.person_month.update_amount_sum()
            instance.person_month.save(update_fields=["amount_sum"])


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

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    employer = models.ForeignKey(Employer, on_delete=models.CASCADE)

    @property
    def person_year(self) -> PersonYear:
        return self.person_month.person_year

    def __str__(self):
        return f"{self.person_month} | {self.employer}"


pre_save.connect(
    MonthlyIncomeReport.pre_save,
    MonthlyAIncomeReport,
    dispatch_uid="MonthlyAIncomeReport_pre_save",
)

post_save.connect(
    MonthlyIncomeReport.post_save,
    MonthlyAIncomeReport,
    dispatch_uid="MonthlyAIncomeReport_post_save",
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

    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )

    trader = models.ForeignKey(
        Employer,
        verbose_name=_("Indhandler"),
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.person_month} | {self.trader}"


post_save.connect(
    MonthlyIncomeReport.post_save,
    MonthlyBIncomeReport,
    dispatch_uid="MonthlyBIncomeReport_save",
)


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

    renteindtægter = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    uddannelsesstøtte = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    honorarer = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    underholdsbidrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    andre_b = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    brutto_b_før_erhvervsvirk_indhandling = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    erhvervsindtægter_sum = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    e2_indhandling = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    brutto_b_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )


class FinalSettlement(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )
    person_year = models.ForeignKey(
        PersonYear, on_delete=models.CASCADE, related_name="final_settlements"
    )
    created = models.DateTimeField(
        auto_now_add=True,
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

    lønindkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    offentlig_hjælp = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    tjenestemandspension = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    alderspension = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    førtidspension = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    arbejdsmarkedsydelse = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    udenlandsk_pensionsbidrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    tilskud_til_udenlandsk_pension = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    dis_gis = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    anden_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteindtægter_bank = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteindtægter_obl = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    andet_renteindtægt = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    uddannelsesstøtte = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    plejevederlag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    underholdsbidrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    udbytte_udenlandske = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    udenlandsk_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    frirejser = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    gruppeliv = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    lejeindtægter_ved_udlejning = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    b_indkomst_andet = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_kost = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_logi = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_bolig = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_telefon = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_bil = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_internet = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_båd = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    fri_andet = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteudgift_realkredit = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteudgift_bank = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteudgift_esu = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteudgift_bsu = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    renteudgift_andet = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    pensionsindbetaling = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    omsætning_salg_på_brættet = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    indhandling = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    ekstraordinære_indtægter = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    virksomhedsrenter = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    virksomhedsrenter_indtægter = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    virksomhedsrenter_udgifter = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    skattemæssigt_resultat = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    ejerandel_pct = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    ejerandel_beløb = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    a_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    b_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    skattefri_b_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    netto_b_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    standard_fradrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    ligningsmæssig_fradrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    anvendt_fradrag = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    skattepligtig_indkomst = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
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


class AnnualIncome(models.Model):
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
    )
    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    load = models.ForeignKey(
        DataLoad,
        null=True,
        on_delete=models.SET_NULL,
    )

    salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    social_benefit_income = models.DecimalField(
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
    other_debt_interest_income = models.DecimalField(
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
    account_extraord_entries_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_business_interest = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_business_interest_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_business_interest_deduct = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_tax_result = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_share_business_percentage = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    account_share_business_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
    shareholder_dividend_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=None, null=True
    )
