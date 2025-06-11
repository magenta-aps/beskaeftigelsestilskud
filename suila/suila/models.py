# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import base64
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from functools import cached_property
from io import BytesIO
from itertools import batched
from os.path import basename
from typing import Iterable, List, Sequence, Tuple

import pandas as pd
import pytz
from common.model_utils import get_amount_from_g68_content
from common.models import User
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import (
    SET_NULL,
    BooleanField,
    Case,
    F,
    Index,
    Q,
    QuerySet,
    Sum,
    TextChoices,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, pre_save
from django.template.loader import get_template
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from lxml import etree
from pypdf import PdfWriter
from simple_history.models import HistoricalRecords
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from suila.data import engine_choices
from suila.integrations.eboks.client import EboksClient, MessageFailureException
from suila.integrations.eskat.responses.data_models import TaxInformation
from suila.model_mixins import PermissionsMixin

logger = logging.getLogger(__name__)


class IncomeType(TextChoices):
    A = "A"
    B = "B"
    U = "U"  # Udbytte / AKAP U1A


class ManagementCommands(TextChoices):
    CALCULATE_STABILITY_SCORE = "calculate_stability_score"
    AUTOSELECT_ESTIMATION_ENGINE = "autoselect_estimation_engine"
    LOAD_ESKAT = "load_eskat"
    LOAD_PRISME_B_TAX = "load_prisme_b_tax"
    IMPORT_U1A_DATA = "import_u1a_data"
    GET_PERSON_INFO_FROM_DAFO = "get_person_info_from_dafo"
    ESTIMATE_INCOME = "estimate_income"
    CALCULATE_BENEFIT = "calculate_benefit"
    EXPORT_BENEFITS_TO_PRISME = "export_benefits_to_prisme"
    SEND_EBOKS = "send_eboks"
    LOAD_PRISME_BENEFITS_POSTING_STATUS = "load_prisme_benefits_posting_status"


class StatusChoices(TextChoices):
    RUNNING = "Kører"
    SUCCEEDED = "Gennemført"
    FAILED = "Fejl"


class WorkingTaxCreditCalculationMethod(PermissionsMixin, models.Model):
    class Meta:
        abstract = True
        permissions = (
            ("use_adminsite_calculator_parameters", "Can use calculation parameters"),
        )

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
            year_income
            - (self.personal_allowance or zero)
            - (self.standard_allowance or zero),
            zero,
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
        zero = Decimal(0)
        allowance = (self.personal_allowance or zero) + (
            self.standard_allowance or zero
        )
        # Calculate breakpoints in graph, by identifying points where the
        # contents of the min() and max() terms are identical,
        # then isolating year_income
        x_points: List[Decimal] = [zero]

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


class DataLoad(PermissionsMixin, models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20)
    parameters = models.JSONField(null=True)


class Year(PermissionsMixin, models.Model):
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


class Person(PermissionsMixin, models.Model):
    class Meta:
        permissions = (("view_data_analysis", "Can view data analysis"),)

    exclude_serialization = ("welcome_letter_id", "welcome_letter_sent_at")
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

    # Når en person er på pause udbetaler vi ved årsopgørelsen (dvs. December).
    paused = models.BooleanField(
        default=False,
        null=False,
        blank=False,
    )

    # If annual income is manually set here, we do not use the estimation engines.
    annual_income_estimate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )

    name = models.TextField(blank=True, null=True)
    address_line_1 = models.TextField(blank=True, null=True)
    address_line_2 = models.TextField(blank=True, null=True)
    address_line_3 = models.TextField(blank=True, null=True)
    address_line_4 = models.TextField(blank=True, null=True)
    address_line_5 = models.TextField(blank=True, null=True)
    full_address = models.TextField(blank=True, null=True)
    foreign_address = models.TextField(blank=True, null=True)
    country_code = models.CharField(blank=True, null=True, max_length=2)
    civil_state = models.TextField(blank=True, null=True)
    location_code = models.TextField(blank=True, null=True)

    cpr_status = models.PositiveSmallIntegerField(blank=True, null=True)
    """Contains the value of the `statuskode` field in CPR.
    This field indicates whether the person is declared missing (status = 70), deceased
    (status = 90), etc.
    See
    https://cprservicedesk.atlassian.net/wiki/spaces/CPR/pages/1722384544/Statuskoder+i+CPR
    for more.
    """

    welcome_letter = models.ForeignKey(
        "SuilaEboksMessage",
        blank=True,
        null=True,
        on_delete=SET_NULL,
    )
    welcome_letter_sent_at = models.DateTimeField(
        # In case the EboksMessage gets deleted, we want to keep
        # the info that the Person has received a message
        blank=True,
        null=True,
        default=None,
    )

    def __str__(self):
        return (
            f"{self.name} / {self.cpr}"
            if self.name and self.cpr
            else str(self.name or self.cpr)
        )

    @property
    def last_year(self) -> PersonYear:
        return self.personyear_set.order_by("-year")[0]

    @classmethod
    def filter_user_instance_permissions(
        cls, qs: QuerySet[Person], user: User, action: str
    ) -> QuerySet:
        if action == "view":
            return qs.filter(cpr=user.cpr)
        return qs.none()

    @property
    def full_address_splitted(self) -> List[str]:
        if not self.full_address:
            return []
        return self.full_address.rsplit(", ", 1)


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


class PersonYear(PermissionsMixin, models.Model):

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
    preferred_estimation_engine_u = models.CharField(
        max_length=100,
        choices=engine_choices,
        null=True,
        default="TwelveMonthsSummationEngine",
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

    # Beregnede felter, sæt kun med signaler
    # Alle tre er fra PersonYearAssessment
    b_income = models.DecimalField(
        null=False,
        blank=False,
        default=Decimal(0),
        max_digits=12,
        decimal_places=2,
    )
    b_expenses = models.DecimalField(
        null=False,
        blank=False,
        default=Decimal(0),
        max_digits=12,
        decimal_places=2,
    )
    catchsale_expenses = models.DecimalField(
        null=False,
        blank=False,
        default=Decimal(0),
        max_digits=12,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.person} ({self.year})"

    @cached_property
    def quarantine_df(self) -> pd.DataFrame:
        from common.utils import get_people_in_quarantine

        return get_people_in_quarantine(self.year.year, [self.person.cpr])

    @property
    def in_quarantine(self) -> bool:
        return (
            settings.ENFORCE_QUARANTINE  # type: ignore
            and self.quarantine_df.loc[self.person.cpr, "in_quarantine"]
        )

    @property
    def quarantine_reason(self) -> str:
        return (
            ""
            if not settings.ENFORCE_QUARANTINE  # type: ignore
            else self.quarantine_df.loc[self.person.cpr, "quarantine_reason"]
        )

    def amount_sum_by_type(self, income_type: IncomeType | None) -> Decimal:
        sum = Decimal(0)
        if income_type in (IncomeType.A, None):
            sum += MonthlyIncomeReport.objects.filter(
                person_month__person_year=self, a_income__gt=0
            ).aggregate(sum=Coalesce(Sum(F("a_income")), Decimal(0)))["sum"]

        if income_type in (IncomeType.B, None):
            # Annual B income always originates from forskudsopgørelse or
            # slutopgørelse.
            sum += self.b_income or 0

        if income_type in (IncomeType.U, None):
            sum += MonthlyIncomeReport.objects.filter(
                person_month__person_year=self, u_income__gt=0
            ).aggregate(sum=Coalesce(Sum(F("u_income")), Decimal(0)))["sum"]

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

    @classmethod
    def filter_user_instance_permissions(
        cls, qs: QuerySet[PersonYear], user: User, action: str
    ) -> QuerySet:
        if action == "view":
            return qs.filter(person__cpr=user.cpr)
        return qs.none()


class PersonMonth(PermissionsMixin, models.Model):

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
    benefit_calculated = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    benefit_transferred = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=0,
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
    prior_benefit_transferred = models.DecimalField(
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

    has_paid_b_tax = models.BooleanField(
        default=False,
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
            self.monthlyincomereport_set.all()
        )

    def __str__(self):
        return f"{self.year}/{self.month} ({self.person})"

    @property
    def year_month(self) -> date:
        return date(self.year, self.month, 1)

    @classmethod
    def filter_user_instance_permissions(
        cls, qs: QuerySet[PersonMonth], user: User, action: str
    ) -> QuerySet:
        if action == "view":
            return qs.filter(person_year__person__cpr=user.cpr)
        return qs.none()

    @property
    def signal(self):
        return self.has_paid_b_tax or self.amount_sum > 0

    @classmethod
    def signal_qs(cls, qs: QuerySet[PersonMonth]) -> QuerySet[PersonMonth]:
        return qs.annotate(
            has_income=Case(
                When(amount_sum__gt=Value(0), then=Value(True)),
                default_value=Value(False),
                output_field=BooleanField(),
            )
        ).annotate(
            has_signal=Case(
                When(
                    Q(has_paid_b_tax=True) | Q(has_income=True),
                    then=Value(True),
                ),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    @property
    def paused(self):
        year = self.person_year.year.year
        month = self.month

        focus_date = pytz.utc.localize(
            datetime(year, month, 1, 0, 0, 0) + relativedelta(months=2)
        )
        now = datetime.now(tz=pytz.utc)

        if focus_date > now:
            return self.person_year.person.paused

        calculate_benefit_jobs_this_month = (
            JobLog.objects.filter(
                name=ManagementCommands.CALCULATE_BENEFIT,
                runtime__month=focus_date.month,
                runtime__year=focus_date.year,
                status=StatusChoices.SUCCEEDED,
            )
            .filter(
                Q(cpr_param__isnull=True) | Q(cpr_param=self.person_year.person.cpr)
            )
            .order_by("-runtime")
        )

        # When we calculate benefit two things can happen:
        # 1) Benefit gets calculated normally
        # 2) The calculated benefit is 0 because the person is paused
        #
        # This is the only place in the code, where being paused matters.
        #
        # We would therefore like the "paused" property to reflect the state a user was
        # in when benefit was calculated.
        #
        # Therefore we set the as_of_date to the date of the last calculate_benefit job
        if calculate_benefit_jobs_this_month:
            as_of_date = calculate_benefit_jobs_this_month[0].runtime
        else:
            if focus_date.month == now.month and focus_date.year == now.year:
                as_of_date = now
            else:
                as_of_date = focus_date

        qs = Person.history.as_of(as_of_date).filter(pk=self.person_year.person.pk)

        if qs:
            return qs[0].paused
        else:
            return False


class Employer(PermissionsMixin, models.Model):
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
        return f"{self.name} ({self.cvr})" if self.name else f"Employer {self.cvr}"


class MonthlyIncomeReport(PermissionsMixin, models.Model):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "person_month"):
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
    u_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
        default=Decimal(0),
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
        q = Decimal("0.01")
        self.a_income = Decimal(
            self.salary_income
            + self.employer_paid_gl_pension_income
            + self.catchsale_income
        ).quantize(q)
        self.u_income = self.u_income.quantize(q)

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
        return f"MonthlyIncomeReport for {self.person_month} ({self.employer})"

    @classmethod
    def sum_queryset(cls, qs: QuerySet["MonthlyIncomeReport"]):
        return qs.aggregate(
            sum=Coalesce(Sum(F("a_income") + F("u_income")), Decimal(0))
        )["sum"]

    @staticmethod
    def pre_save(sender, instance: MonthlyIncomeReport, *args, **kwargs):
        instance.month = instance.person_month.month
        instance.year = instance.person_month.year
        instance.person = instance.person_month.person
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
        if update_fields is None or "a_income" in update_fields:
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


class BTaxPayment(PermissionsMixin, models.Model):
    """This model is used for tracking whether the person has actually paid tax on their
    B income for a given month.
    They are only eligible for receiving benefits due to B income if they have indeed
    paid tax on their B income.
    Note that we only get a total amount of B tax paid - it is not split on the
    different types of B income.
    Also note that the B tax paid may differ from the B tax that was charged.
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "cpr",
                "amount_paid",
                "amount_charged",
                "date_charged",
                "rate_number",
                name="unique_btaxpayment",
            )
        ]

    person_month = models.ForeignKey(
        PersonMonth,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    cpr = models.CharField(
        max_length=10,
        null=True,
        blank=True,
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


class IncomeEstimate(PermissionsMixin, models.Model):

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
    def qs_offset(qs: Iterable[IncomeEstimate]) -> Decimal:
        estimated_year_result = Decimal(0)
        actual_year_result = Decimal(0)
        for item in qs:
            estimated_year_result += item.estimated_year_result
            if item.actual_year_result:
                actual_year_result += item.actual_year_result
        absdiff = abs(estimated_year_result - actual_year_result)
        return (absdiff / actual_year_result) if actual_year_result else Decimal(0)


class PersonYearEstimateSummary(PermissionsMixin, models.Model):
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


class PersonYearAssessment(PermissionsMixin, models.Model):
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
    valid_from = models.DateTimeField(
        default=datetime(1900, 1, 1, 0, 0, 0),
        null=False,
        blank=False,
    )
    latest = models.BooleanField(default=True)

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
    benefits_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    business_turnover = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    catch_sale_factory_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    catch_sale_market_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    goods_comsumption = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    operating_costs_catch_sale = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    operating_expenses_own_company = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    tax_depreciation = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    bussiness_interest_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    bussiness_interest_expenses = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    extraordinary_bussiness_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )
    extraordinary_bussiness_expenses = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal(0), null=False
    )

    @property
    def assessed_b_incomes(self) -> Decimal:
        incomes = (
            self.business_turnover
            + self.catch_sale_market_income
            + self.care_fee_income
            + self.capital_income
            + self.other_b_income
        )
        return Decimal(incomes).quantize(Decimal("0.01"))

    @property
    def assessed_b_expenses(self) -> Decimal:
        expenses = self.goods_comsumption + self.operating_expenses_own_company
        return Decimal(expenses).quantize(Decimal("0.01"))

    @property
    def assessed_catchsale_expenses(self) -> Decimal:
        # Sum of expenses that must be subtracted from every estimation
        return max(
            min(
                self.operating_costs_catch_sale,
                self.catch_sale_market_income + self.catch_sale_factory_income,
            ),
            Decimal(0),
        )

    @staticmethod
    def update_personyear_fields(qs: QuerySet[PersonYearAssessment] | None = None):
        if qs is None:
            qs = PersonYearAssessment.objects.all()
        qs = qs.filter(latest=True).select_related("person_year")
        for batch in batched(qs.iterator(2000), 2000):
            to_update: List[PersonYear] = []
            for assessment in batch:
                person_year: PersonYear = assessment.person_year
                person_year.b_income = assessment.assessed_b_incomes
                person_year.b_expenses = assessment.assessed_b_expenses
                person_year.catchsale_expenses = assessment.assessed_catchsale_expenses
                to_update.append(person_year)
            PersonYear.objects.bulk_update(
                to_update, ("b_income", "b_expenses", "catchsale_expenses")
            )

    @staticmethod
    def update_latest(qs: QuerySet[PersonYearAssessment] | None = None):
        if qs is None:
            qs = PersonYearAssessment.objects.all()
        latest = qs.order_by("person_year", "-valid_from").distinct("person_year")
        latest.update(latest=True)
        PersonYearAssessment.objects.exclude(id__in=latest).update(latest=False)

    @staticmethod
    def post_save(
        sender,
        instance: PersonYearAssessment,
        created: bool,
        raw: bool,
        using: str,
        update_fields: Sequence[str] | None,
        **kwargs,
    ):
        qs = PersonYearAssessment.objects.filter(person_year=instance.person_year)
        PersonYearAssessment.update_latest(qs)
        PersonYearAssessment.update_personyear_fields(qs)


post_save.connect(
    PersonYearAssessment.post_save,
    PersonYearAssessment,
    dispatch_uid="PersonYearAssessment_post_save",
)


class PrismeAccountAlias(PermissionsMixin, models.Model):
    class Meta:
        unique_together = [("tax_municipality_location_code", "tax_year")]

    alias = models.TextField()
    """The account alias itself"""

    tax_municipality_location_code = models.TextField()
    """The 'myndighedskode' of the municipality issuing the benefit"""

    tax_year = models.PositiveSmallIntegerField()
    """The 'skatteår' in which the Prisme postings should be made"""

    def __str__(self):
        return f"{self.alias}"

    @property
    def tax_municipality_five_digit_code(self) -> str:
        return self.alias[-7:-2]


class PrismeBatch(PermissionsMixin, models.Model):
    class Meta:
        permissions = (("can_download_reports", "Can download CSV reports"),)

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


class PrismePostingStatusFile(models.Model):
    filename = models.TextField(unique=True)
    """Contains the filename of the the "bogføringsstatus" (posting status) CSV file"""

    created = models.DateTimeField(auto_now_add=True)


class PrismeBatchItem(PermissionsMixin, models.Model):
    class Meta:
        unique_together = ("prisme_batch", "person_month")

    class PostingStatus(models.TextChoices):
        Sent = "sent", _("Sendt til udbetaling")
        Posted = "posted", _("Udbetaling gennemført")
        Failed = "failed", _("Fejl i udbetaling")

    prisme_batch = models.ForeignKey(
        PrismeBatch,
        on_delete=models.CASCADE,
    )

    person_month = models.OneToOneField(
        PersonMonth,
        on_delete=models.CASCADE,
    )

    posting_status_file = models.ForeignKey(
        PrismePostingStatusFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    """Indicates the posting status file where we got the posted/failed status for this
    Prisme batch item."""

    g68_content = models.TextField()

    g69_content = models.TextField()

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

    paused = models.BooleanField(
        default=False,
        null=False,
        blank=False,
    )

    @property
    def amount(self):
        return get_amount_from_g68_content(self.g68_content)


class AnnualIncome(PermissionsMixin, models.Model):
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
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    public_assistance_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    retirement_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    disability_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    ignored_benefits = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    occupational_benefit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    foreign_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    subsidy_foreign_pension_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    dis_gis_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    other_a_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    deposit_interest_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    bond_interest_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    other_interest_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    education_support_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    care_fee_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    alimony_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    foreign_dividend_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    foreign_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_journey_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    group_life_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    rental_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    other_b_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_board_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_lodging_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_housing_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_phone_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_car_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_internet_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_boat_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    free_other_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    pension_payment_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    catch_sale_market_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    catch_sale_factory_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    account_tax_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    account_share_business_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )
    shareholder_dividend_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=None,
        null=True,
        blank=True,
    )


class JobLog(PermissionsMixin, models.Model):
    """
    model which keeps track of:
        - which jobs were run
        - On what date
        - Whether they finished
        - With which args/kwargs
    """

    name = models.TextField(choices=ManagementCommands)
    runtime = models.DateTimeField(auto_now_add=True)
    runtime_end = models.DateTimeField(default=None, null=True)
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


class EboksMessage(PermissionsMixin, models.Model):
    created = models.DateTimeField(auto_now_add=True)
    sent = models.DateTimeField(null=True)
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
    contents = models.FileField(
        null=True, upload_to=settings.LOCAL_EBOKS_PDF_STORAGE  # type: ignore
    )

    @classmethod
    def dispatch(
        cls,
        cpr_cvr: str,
        title: str,
        content_type: int,
        pdf_data: bytes,
        client: EboksClient | None = None,
    ) -> EboksMessage:
        message = cls(cpr_cvr=cpr_cvr, title=title, content_type=content_type)
        message.set_pdf_data(pdf_data)
        message.send(client=client)
        return message

    def set_pdf_data(self, pdf_data: bytes):
        name = f"{uuid.uuid4()}.pdf"
        self.contents.save(
            content=File(BytesIO(pdf_data), name=name), name=name, save=False
        )

    @cached_property
    def xml(self):
        pdf_data = self.contents.read()
        return self.generate_xml(self.cpr_cvr, self.title, self.content_type, pdf_data)

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


class SuilaEboksMessage(EboksMessage):

    type_map = {
        "opgørelse": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Suila-tapit udbetaling for {month}",
            "template_folder": "suila/eboks/opgørelse",
            "templates": {
                "kl": get_template("suila/eboks/opgørelse/kl.html"),
                "da": get_template("suila/eboks/opgørelse/da.html"),
            },
        },
        "afventer": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Suila-tapit udbetaling for {month}",
            "template_folder": "suila/eboks/afventer",
            "templates": {
                "kl": get_template("suila/eboks/afventer/kl.html"),
                "da": get_template("suila/eboks/afventer/da.html"),
            },
        },
    }

    welcome_letter = "opgørelse"
    month_names = {
        "da": [
            "januar",
            "februar",
            "marts",
            "april",
            "maj",
            "juni",
            "juli",
            "august",
            "september",
            "oktober",
            "november",
            "december",
        ],
        "kl": [
            "januaari",
            "februaari",
            "marsi",
            "apriili",
            "maaji",
            "juuni",
            "juuli",
            "aggusti",
            "septembari",
            "oktobari",
            "novembari",
            "decembari",
        ],
    }

    person_month = models.ForeignKey(
        PersonMonth, null=False, blank=False, on_delete=models.CASCADE
    )

    type = models.CharField(
        max_length=10,
        choices=(
            ("opgørelse", "Opgørelse"),
            ("afventer", "Afventer"),
        ),
        null=False,
        blank=False,
    )

    @property
    def attrs(self):
        return self.type_map[self.type]

    @property
    def month(self):
        return self.person_month.month

    @property
    def year(self) -> int:
        return self.person_year.year_id

    @cached_property
    def person_year(self) -> PersonYear:
        return self.person_month.person_year

    @property
    def person(self):
        return self.person_month.person

    @cached_property
    def context(self):
        quant = Decimal("0.01")
        year_range = range(self.year, self.year - 3, -1)
        year_map = [[self.person_month]] + [
            PersonMonth.objects.filter(
                person_year__person=self.person, person_year__year_id=y
            )
            for y in year_range
        ]
        return {
            "person": self.person,
            "year": self.year,
            "month": self.month,
            "personyear": self.person_month.person_year,
            "personmonth": self.person_month,
            "sum_income": (self.person_month.estimated_year_result or Decimal(0))
            + self.person_year.b_income
            - self.person_year.b_expenses
            - self.person_year.catchsale_expenses,
            "income": {
                "catchsale_income": [
                    Decimal(
                        sum(
                            [
                                report.catchsale_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "salary_income": [
                    Decimal(
                        sum(
                            [
                                report.salary_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "btax_paid": [
                    Decimal(
                        sum(
                            [
                                payment.amount_paid
                                for pm in months
                                for payment in pm.btaxpayment_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "capital_income": [
                    Decimal(
                        sum(
                            [
                                report.u_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
            },
        }

    def html(self, language: str):
        template = self.attrs["templates"][language]
        context = {
            **self.context,
            "month_name": self.month_names[language][self.month - 1],
        }
        return template.render(context)

    @cached_property
    def html_kl(self):
        return self.html("kl")

    @cached_property
    def html_da(self):
        return self.html("da")

    @cached_property
    def pdf(self) -> bytes:
        font_config = FontConfiguration()
        writer = PdfWriter()
        data = BytesIO()
        for html in (self.html_kl, self.html_da):
            pdf_data = HTML(string=html).write_pdf(font_config=font_config)
            writer.append(BytesIO(pdf_data))
            writer.write_stream(data)
        data.seek(0)
        return data.read()

    def update_fields(self, force_update=False):
        month_name = self.month_names["da"][self.month - 1]
        self.title = self.attrs["title"].format(month=month_name)
        self.content_type = self.attrs["content_type"]
        self.cpr_cvr = self.person_month.person.cpr
        if not self.contents or force_update:
            self.set_pdf_data(self.pdf)

    def send(self, client: EboksClient | None = None):
        self.update_fields()
        super().send(client)

    def update_welcome_letter(self):
        if self.type == self.welcome_letter and self.sent is not None:
            self.person.welcome_letter = self
            self.person.welcome_letter_sent_at = self.sent
            self.person.save(update_fields=("welcome_letter", "welcome_letter_sent_at"))

    @staticmethod
    def pre_save(sender, instance: SuilaEboksMessage, *args, **kwargs):
        instance.update_fields()


pre_save.connect(
    SuilaEboksMessage.pre_save,
    SuilaEboksMessage,
    dispatch_uid="SuilaEboksMessage_pre_save",
)


class PersonYearU1AAssessment(PermissionsMixin, models.Model):
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


class Note(PermissionsMixin, models.Model):
    personyear = models.ForeignKey(PersonYear, null=False, on_delete=models.CASCADE)
    text = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    history = HistoricalRecords(
        history_change_reason_field=models.TextField(null=True),
        related_name="history_entries",
    )


def get_attachment_path(instance, filename):
    return (
        f"note/{instance.note.personyear.year.year}/"
        f"{instance.note.personyear.person.cpr}/"
        f"{instance.note.pk}/{filename}"
    )


class NoteAttachment(PermissionsMixin, models.Model):
    class Meta:
        ordering = ["file"]

    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=get_attachment_path)
    content_type = models.CharField(max_length=100)

    @property
    def filename(self):
        return basename(self.file.name)
