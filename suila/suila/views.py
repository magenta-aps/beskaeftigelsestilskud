# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools
import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from math import ceil
from typing import Any, Iterable
from urllib.parse import urlencode

from common.fields import CPRField
from common.models import User
from common.utils import SuilaJSONEncoder, get_user_who_pressed_pause, omit
from common.view_mixins import BaseGetFormView, ViewLogMixin
from dateutil.relativedelta import relativedelta
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction
from django.db.models import CharField, F, IntegerChoices, Max, Q, QuerySet, Value
from django.db.models.functions import Cast, LPad
from django.forms.models import BaseInlineFormSet, fields_for_model, model_to_dict
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import date as format_date
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.formats import number_format
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop, override
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.generic import DetailView, FormView, ListView, TemplateView
from django.views.generic.base import ContextMixin
from django.views.generic.detail import BaseDetailView
from django.views.generic.edit import UpdateView
from django_filters import ChoiceFilter, Filter, FilterSet, MultipleChoiceFilter
from django_filters.views import FilterView
from django_tables2 import (
    BooleanColumn,
    Column,
    SingleTableMixin,
    Table,
    TemplateColumn,
)
from django_tables2.columns.linkcolumn import BaseLinkColumn
from django_tables2.utils import Accessor
from login.view_mixins import LoginRequiredMixin

from suila.data import engine_choices
from suila.dates import get_pause_effect_date, get_payment_date
from suila.forms import (
    CalculationParametersForm,
    CalculatorForm,
    ConfirmationForm,
    IncomeSignalFilterForm,
    NoteAttachmentFormSet,
    NoteForm,
    PauseForm,
    PersonAnnualIncomeEstimateForm,
    PersonYearEstimationEngineForm,
)
from suila.integrations.eboks.client import EboksClient
from suila.models import (
    BTaxPayment,
    Employer,
    IncomeType,
    ManagementCommands,
    MonthlyIncomeReport,
    Note,
    NoteAttachment,
    PauseReasonChoices,
    Person,
    PersonMonth,
    PersonYear,
    StandardWorkBenefitCalculationMethod,
    SuilaEboksMessage,
    WorkingTaxCreditCalculationMethod,
    Year,
)
from suila.view_mixins import MustHavePersonYearMixin, PermissionsRequiredMixin

logger = logging.getLogger(__name__)


class RootView(LoginRequiredMixin, ViewLogMixin, TemplateView):
    template_name = "suila/root.html"

    def get(self, request, *args, **kwargs):
        self.log_view()
        return super().get(request, *args, **kwargs)


class NameColumn(BaseLinkColumn):
    def __init__(self, *args, **kwargs):
        linkify = dict(viewname="suila:person_detail", args=[Accessor("pk")])
        kwargs.setdefault("linkify", linkify)
        super().__init__(*args, **kwargs)


class PersonTable(Table):
    name = NameColumn(verbose_name=_("Navn"))
    cpr = Column(
        accessor=Accessor("_cpr"),
        order_by=Accessor("_cpr"),
        verbose_name=_("CPR-nummer"),
        orderable=False,
        linkify=dict(viewname="suila:person_detail", args=[Accessor("pk")]),
    )
    full_address = Column(verbose_name=_("Adresse"))


class PersonPauseTable(Table):
    name = NameColumn(verbose_name=_("Navn"))
    cpr = Column(
        verbose_name=_("CPR-nummer"),
        orderable=True,
    )
    allow_pause = BooleanColumn(
        verbose_name=_("Må selv genoptage udbetalinger"),
        orderable=True,
    )
    pause_start_date = Column(
        verbose_name=_("Startdato for udbetalingspause"),
        empty_values=(),
        orderable=False,
    )
    pause_reason = Column(
        verbose_name=_("Årsag til pause"),
        orderable=True,
        default="-",
    )
    pause_note = Column(
        verbose_name=_("Seneste notat"),
        empty_values=(),
        orderable=False,
    )

    def render_pause_start_date(self, value, record):
        last_change = record.last_change("paused")
        return last_change.date() if last_change else "-"

    def render_pause_note(self, value, record):
        last_note = (
            Note.objects.filter(
                personyear__person__pk=record.pk,
                text__icontains="udbetalingspause",
            )
            .order_by("-created")
            .first()
        )
        if not last_note:
            return "-"
        parts = last_note.text.split("\n")
        return parts[-1].strip()


class CPRFilter(Filter):
    field_class = CPRField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",  # smaller input
                    "style": "max-width: 250px;",  # limits width
                }
            ),
        )
        super().__init__(*args, **kwargs)


class PersonFilterSet(FilterSet):
    cpr = CPRFilter("_cpr", label=_("CPR-nummer"), required=True)


DEFAULT_PAUSE_REASONS_FILTER = [str(i) for i in range(1, 8)]
DEFAULT_ALLOW_PAUSE_FILTER = False


class PersonPauseFilterSet(FilterSet):
    cpr = CPRFilter("_cpr", label=_("CPR-nummer"), required=False)

    allow_pause = ChoiceFilter(
        field_name="allow_pause",
        label=_("Må selv genoptage udbetalinger"),
        choices=[
            (True, _("Ja")),
            (False, _("Nej")),
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select form-select-sm",
                "style": "max-width: 250px;",
            }
        ),
        required=False,
        initial=DEFAULT_ALLOW_PAUSE_FILTER,
    )
    pause_reason = MultipleChoiceFilter(
        field_name="pause_reason",
        label=_("Årsag til pause"),
        choices=PauseReasonChoices.choices,
        conjoined=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "text-dark",
                "style": "color:black;",
            }
        ),
        initial=DEFAULT_PAUSE_REASONS_FILTER,
    )


class YearMonthMixin:
    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["year"] = self.year
        context_data["month"] = self.month
        return context_data

    @cached_property
    def year(self) -> int:
        try:
            return int(self.request.GET.get("year"))  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            return timezone.now().year

    @cached_property
    def month(self) -> int:
        if self.year < timezone.now().year:
            return 12  # For past years, always use last month of year
        else:
            try:
                return int(self.request.GET.get("month"))  # type: ignore[attr-defined]
            except (TypeError, ValueError):
                return timezone.now().month


class PersonYearMonthMixin(YearMonthMixin):
    @cached_property
    def person_pk(self) -> int:
        return self.kwargs["pk"]  # type: ignore[attr-defined]

    @cached_property
    def person_year(self):
        personyear = get_object_or_404(
            PersonYear,
            year_id=self.year,
            person_id=self.person_pk,
        )
        return personyear


class PersonSearchView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    SingleTableMixin,
    ViewLogMixin,
    FilterView,
):
    model = Person
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "suila/person_search.html"
    matomo_pagename = "Personsøgning"
    required_model_permissions = ["suila.view_person"]

    def get_queryset(self):
        qs = Person.filter_user_permissions(
            super().get_queryset(),
            self.request.user,  # type: ignore
            "view",
        )
        # Add zero-padded text version of CPR to ensure proper display and sorting
        qs = qs.annotate(_cpr=LPad(Cast("cpr", CharField()), 10, Value("0")))
        # Set initial sorting (can be overridden by user)
        qs = qs.order_by("_cpr")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.log_view(context["table"].page.object_list.data)
        return context


class PersonPauseListView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    SingleTableMixin,
    ViewLogMixin,
    FilterView,
):
    model = Person
    table_class = PersonPauseTable
    filterset_class = PersonPauseFilterSet
    template_name = "suila/person_pause_list.html"
    matomo_pagename = "Person - pauseliste"

    required_model_permissions = [
        "suila.view_person",
    ]

    def get_queryset(self):
        qs = Person.objects.filter(paused=True)

        # Apply default pause_reason filter if none provided
        if not self.request.GET.getlist("pause_reason"):
            default_reasons = DEFAULT_PAUSE_REASONS_FILTER
            qs = qs.filter(pause_reason__in=default_reasons)

        # Apply default allow_pause filter if not provided
        if "allow_pause" not in self.request.GET:
            qs = qs.filter(allow_pause=DEFAULT_ALLOW_PAUSE_FILTER)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.log_view(context["table"].page.object_list.data)
        return context


class PersonMonthTable(Table):
    month = TemplateColumn(
        template_name="suila/table_columns/month.html",
        verbose_name=_("Måned"),
    )
    payout_date = TemplateColumn(
        template_name="suila/table_columns/payout_date.html",
        verbose_name=_("Forventet udbetalingsdato"),
    )
    benefit = TemplateColumn(
        template_name="suila/table_columns/benefit.html",
        verbose_name=_("Forventet beløb til udbetaling"),
    )
    status = TemplateColumn(
        template_name="suila/table_columns/status.html",
        verbose_name=_("Status"),
    )


@dataclass(frozen=True)
class RelevantPersonMonth:
    person_month: PersonMonth
    next_payout_date: date
    quarantine_weight: int


class PersonDetailView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearMonthMixin,
    SingleTableMixin,
    ViewLogMixin,
    MustHavePersonYearMixin,
    DetailView,
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail.html"
    required_object_permissions = ["view"]
    table_class = PersonMonthTable
    matomo_pagename = "Persondetaljer - forside"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        user = self.request.user

        # Get the "currently relevant" person month
        relevant_person_month: RelevantPersonMonth = self.get_relevant_person_month()

        # True if user is looking at a past year (usually not the case, as this is
        # currently hidden from users.)
        context_data["year_in_past"] = (
            (
                relevant_person_month.person_month.person_year.year.year
                < (date.today() - relativedelta(months=2)).year
            )
            if relevant_person_month
            else self.person_year.year.year < date.today().year
        )

        if relevant_person_month is not None:
            person_month = relevant_person_month.person_month
            person_year = person_month.person_year
            person = person_year.person
            estimated_year_result = (
                (relevant_person_month.person_month.estimated_year_result or Decimal(0))
                - person_year.catchsale_expenses
                + (person_year.b_income - person_year.b_expenses)
            )

            paused_last_change = person.last_change("paused")
            now = timezone.now()
            if paused_last_change and person.paused:
                person_month_when_person_was_paused: PersonMonth = (
                    self.get_relevant_person_month(
                        paused_last_change.year, paused_last_change.month
                    )
                ).person_month

                pause_effect_date = get_pause_effect_date(
                    person_month_when_person_was_paused
                )
            else:
                pause_effect_date = get_pause_effect_date(person_month)

            if pause_effect_date and pause_effect_date >= now.date():
                show_pause_effect_date = True
            else:
                show_pause_effect_date = False
                pause_effect_date = now.date()

            civil_state_last_change = person.last_change("civil_state")

            send_eboks_letter_when_pausing = settings.SEND_EBOKS_LETTER_WHEN_PAUSING

            pause_reasons = [
                c
                for c in PauseReasonChoices.choices
                if c[0] not in [PauseReasonChoices.DEATH, PauseReasonChoices.MISSING]
            ]

            engine_a = person_year.preferred_estimation_engine_a
            engine_u = person_year.preferred_estimation_engine_u

            last_calculation_engines = person_year.engines_used_for_latest_calculation

            last_engine_a = last_calculation_engines[IncomeType.A]
            last_engine_u = last_calculation_engines[IncomeType.U]

            if (last_engine_a and last_engine_a != engine_a) or (
                last_engine_u and last_engine_u != engine_u
            ):
                estimation_engine_changed = True
            else:
                estimation_engine_changed = False

            context_data.update(
                {
                    "show_next_payment": True,
                    "next_payout_date": relevant_person_month.next_payout_date,
                    "benefit_calculated": person_month.benefit_calculated,
                    "estimated_year_benefit": person_month.estimated_year_benefit,
                    "estimated_year_result": estimated_year_result,
                    "paused": person.paused,
                    "allow_pause": person.allow_pause,
                    "can_pause": person.allow_pause and (user.cpr == person.cpr),
                    "can_unpause": not (  # Paused person who is dead or missing
                        person.paused  # may not be unpaused
                        and person.pause_reason
                        in (PauseReasonChoices.MISSING, PauseReasonChoices.DEATH)
                    ),
                    "person_id": person.pk,
                    "person_year_id": person_year.pk,
                    "next_year": person_year.year.year + 1,
                    "in_quarantine": person_year.in_quarantine,
                    "quarantine_reason": person_year.quarantine_reason,
                    "quarantine_weight": relevant_person_month.quarantine_weight,
                    "user_who_pressed_pause": get_user_who_pressed_pause(person),
                    "year": person_year.year.year,
                    "month": person_month.month,
                    "manually_entered_income": person.annual_income_estimate,
                    "manually_entered_income_last_change": person.last_change(
                        "annual_income_estimate"
                    ),
                    "paused_last_change": paused_last_change,
                    "civil_state_last_change": civil_state_last_change,
                    "now": now,
                    "manually_entered_income_formset": NoteAttachmentFormSet(),
                    "pause_formset": NoteAttachmentFormSet(),
                    "estimation_engine_formset": NoteAttachmentFormSet(),
                    "engine_choices": engine_choices,
                    "engine_a": engine_a,
                    "engine_u": engine_u,
                    "pause_effect_date": pause_effect_date,
                    "show_pause_effect_date": show_pause_effect_date,
                    "pause_reasons": pause_reasons,
                    "pause_reason": person.pause_reason,
                    "send_eboks_letter_when_pausing": send_eboks_letter_when_pausing,
                    "estimation_engine_changed": estimation_engine_changed,
                }
            )
        else:
            context_data["show_next_payment"] = False

        self.log_view(self.object)
        return context_data

    def get_relevant_person_month(
        self, year=None, month=None
    ) -> RelevantPersonMonth | None:
        max_date: date = date(
            year or self.year, month or self.month, 1
        ) - relativedelta(months=2)
        try:
            person_months = PersonMonth.objects.filter(
                person_year__person=self.object,
                person_year__year__year=max_date.year,
                month__lte=max_date.month,
            )
            person_months_with_income_estimate = person_months.filter(
                incomeestimate__isnull=False
            ).distinct()

            if person_months_with_income_estimate.exists():
                person_month = person_months_with_income_estimate.latest("month")
            else:
                person_month = person_months.latest("month")

        except PersonMonth.DoesNotExist:
            logger.error(
                "No PersonMonth found for person %r (max_date=%r)",
                self.person_pk,
                max_date,
            )
            return None
        else:
            quarantine_weights = settings.QUARANTINE_WEIGHTS  # type: ignore[misc]
            return RelevantPersonMonth(
                person_month=person_month,
                next_payout_date=get_payment_date(
                    person_month.person_year.year.year,
                    person_month.month,
                ),
                quarantine_weight=quarantine_weights[person_month.month - 1],
            )

    def get_table_data(self):
        relevant_person_month = self.get_relevant_person_month()
        if relevant_person_month:
            return (
                PersonMonth.objects.select_related(
                    "person_year__person", "person_year__year"
                )
                .filter(
                    person_year=relevant_person_month.person_month.person_year,
                    month__lte=relevant_person_month.person_month.month,
                )
                .order_by("month")
            )
        else:
            return []

    def get_table_kwargs(self):
        return {"orderable": False}


class IncomeSignalType(IntegerChoices):
    Lønindkomst = (0, _("Lønindkomst"))
    Indhandling = (1, _("Indhandling"))
    BetaltBSkat = (2, _("Betalt B-skat"))
    Udbytte = (3, _("Udbytte"))
    Pension = (4, _("Pensionsindbetaling"))


@dataclass(frozen=True)
class IncomeSignal:
    signal_type: IncomeSignalType
    source: str
    amount: Decimal
    date: date

    @property
    def filter_key(self) -> str:
        use_source = (
            IncomeSignalType.Lønindkomst,
            IncomeSignalType.Indhandling,
            IncomeSignalType.Udbytte,
            IncomeSignalType.Pension,
        )
        if self.signal_type in use_source:
            return self.source
        elif self.signal_type is IncomeSignalType.BetaltBSkat:
            return gettext("Betalte B-skatter")
        else:
            raise ValueError(
                "cannot determine filter_key for %r" % self
            )  # pragma: no cover


class IncomeSumsBySignalTypeTable(Table):
    signal_type = TemplateColumn(
        template_name="suila/table_columns/signal_type.html",
        verbose_name=_("Signaltype"),
    )
    current_month_sum = TemplateColumn(
        template_name="suila/table_columns/amount.html",
        verbose_name=_("Indeværende måned"),
    )
    current_year_sum = TemplateColumn(
        template_name="suila/table_columns/amount.html",
        verbose_name=_("Samlet for året"),
    )

    def __init__(
        self,
        income_signals: list[IncomeSignal],
        year: int,
        month: int,
        *args,
        **kwargs,
    ):
        self.year: int = year
        self.month: int = month

        def sum_amounts(
            signal_type: IncomeSignalType,
            signals: list[IncomeSignal],
            month: int | None = None,
        ) -> Decimal:
            signals_of_type: list[IncomeSignal] = [
                signal for signal in signals if signal.signal_type == signal_type
            ]
            if month is None:
                if len(signals_of_type) == 0:
                    return Decimal("0")
                return sum(signal.amount for signal in signals_of_type)  # type: ignore
            else:
                signals_of_type_and_month: list[IncomeSignal] = [
                    signal for signal in signals_of_type if signal.date.month == month
                ]
                if len(signals_of_type_and_month) == 0:
                    return Decimal("0")
                return sum(  # type: ignore
                    signal.amount for signal in signals_of_type_and_month
                )

        data: list[dict] = [
            {
                "signal_type": signal_type,
                "current_month_sum": sum_amounts(
                    signal_type, income_signals, month=month
                ),
                "current_year_sum": sum_amounts(signal_type, income_signals),
            }
            for signal_type in IncomeSignalType
        ]

        super().__init__(data, *args, **kwargs)

    def before_render(self, request):
        # Create string such as "Marts 2025" from year and month
        month: date = date(self.year, self.month, 1)
        month_formatted: str = format_date(month, "F Y").capitalize()
        # Use this string as the title of the month sum column
        self.columns["current_month_sum"].column.verbose_name = month_formatted


class IncomeSignalTable(Table):
    date = TemplateColumn(
        template_name="suila/table_columns/date.html",
        verbose_name=_("Dato"),
    )
    amount = TemplateColumn(
        template_name="suila/table_columns/amount.html",
        verbose_name=_("Beløb"),
    )
    signal_type = TemplateColumn(
        template_name="suila/table_columns/signal_type.html",
        verbose_name=_("Signaltype"),
    )
    source = Column(verbose_name=_("Kilde"))


class PersonDetailIncomeView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearMonthMixin,
    ViewLogMixin,
    MustHavePersonYearMixin,
    DetailView,
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_income.html"
    required_object_permissions = ["view"]
    matomo_pagename = "Persondetaljer - indkomst"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        # Determine which month is the latest month containing income signals.
        latest_income_month = self._get_latest_income_month()

        # Table summing income by signal type
        context_data["sum_table"] = IncomeSumsBySignalTypeTable(
            self.get_income_signals(),
            self.year,
            latest_income_month,
            orderable=False,
        )

        # Filter for the detail table
        context_data["detail_table_filter"] = filter_form = IncomeSignalFilterForm(
            signals=self.get_income_signals(),
            data=self.request.GET,
        )

        # Filter signal list in detail table based on filter form
        signals: list[IncomeSignal]
        if filter_form.is_valid() and filter_form.cleaned_data["filter_key"] != "":
            filter_key: str = filter_form.cleaned_data["filter_key"]
            signals = [
                signal
                for signal in self.get_income_signals()
                if signal.filter_key == filter_key
            ]
        else:
            signals = self.get_income_signals()

        # Table showing a row for each signal in this person year
        context_data["detail_table"] = IncomeSignalTable(
            signals,
            order_by=self.request.GET.get("sort"),
        )

        # Queryset of person years available for this person
        context_data["available_person_years"] = PersonYear.objects.filter(
            person=self.person_year.person
        ).order_by("-year__year")

        self.log_view(self.object)
        return context_data

    def get_income_signals(self) -> list[IncomeSignal]:
        return sorted(
            itertools.chain(
                self.get_monthly_income_signals(),
                self.get_b_tax_payments(),
            ),
            # Default ordering: newest first, then by signal type, then by source
            key=lambda signal: (
                date.max - signal.date,
                signal.signal_type,
                signal.source,
            ),
        )

    def get_monthly_income_signals(self) -> Iterable[IncomeSignal]:
        def format_employer(employer: Employer | None):
            if employer is None:
                return gettext("Ikke oplyst")
            if employer.name is None:
                return gettext("CVR: %(cvr)s") % {"cvr": employer.cvr}
            else:
                return employer.name

        qs = MonthlyIncomeReport.objects.filter(
            person_month__person_year=self.person_year,
        )
        for item in qs:
            if item.salary_income > 0:
                yield IncomeSignal(
                    IncomeSignalType.Lønindkomst,
                    format_employer(item.employer),
                    item.salary_income,
                    item.person_month.year_month,
                )
            if item.catchsale_income > 0:
                yield IncomeSignal(
                    IncomeSignalType.Indhandling,
                    format_employer(item.employer),
                    item.catchsale_income,
                    item.person_month.year_month,
                )
            if item.u_income > 0:
                yield IncomeSignal(
                    IncomeSignalType.Udbytte,
                    format_employer(item.employer),
                    item.u_income,
                    item.person_month.year_month,
                )
            if item.employer_paid_gl_pension_income > 0:
                yield IncomeSignal(
                    IncomeSignalType.Pension,
                    format_employer(item.employer),
                    item.employer_paid_gl_pension_income,
                    item.person_month.year_month,
                )

    def get_b_tax_payments(self) -> Iterable[IncomeSignal]:
        qs = BTaxPayment.objects.filter(
            person_month__isnull=False, person_month__person_year=self.person_year
        )
        for item in qs:
            if item.amount_paid > 0:
                yield IncomeSignal(
                    IncomeSignalType.BetaltBSkat,
                    gettext("Rate: %(rate_number)s")
                    % {"rate_number": item.rate_number},
                    item.amount_paid,
                    item.person_month.year_month,  # type: ignore[union-attr]
                )

    def _get_latest_income_month(self) -> int:
        def month(qs: QuerySet, default: int = 1) -> int:
            return qs.aggregate(month=Max("person_month__month"))["month"] or default

        latest_monthly_income_report_month: int = month(
            MonthlyIncomeReport.objects.filter(
                Q(person_month__person_year=self.person_year),
                Q(a_income__gt=0) | Q(u_income__gt=0),
            )
        )

        latest_b_tax_payment_month: int = month(
            BTaxPayment.objects.filter(
                person_month__isnull=False,
                person_month__person_year=self.person_year,
                amount_paid__gt=0,
            )
        )

        # `PersonYearU1AAssessment` do not reference `PersonMonth` but only `PersonYear`
        # For now, we assume that they "belong" to January.
        # TODO: revisit when/if `PersonYearU1AAssessment` refer to a `PersonMonth`.
        latest_u1a_assessment_month = 1

        return min(
            self.month,  # never use a later month than the current calendar month
            max(
                [
                    latest_monthly_income_report_month,
                    latest_b_tax_payment_month,
                    latest_u1a_assessment_month,
                ]
            ),
        )


class PersonDetailEboksPreView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearMonthMixin,
    ViewLogMixin,
    DetailView,
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_eboks_preview.html"
    required_model_permissions = [
        "suila.view_person",
    ]
    matomo_pagename = "Persondetaljer - ebokspreview"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update(
            {
                "months": self.person_year.personmonth_set.all().order_by("month"),
                "available_person_years": PersonYear.objects.filter(
                    person=self.person_year.person
                ).order_by("-year__year"),
            }
        )
        self.log_view(self.person_year)
        return context_data


class PersonDetailEboksSendView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearMonthMixin,
    ViewLogMixin,
    DetailView,
    FormView,
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_eboks_send.html"
    required_model_permissions = [
        "suila.add_eboksmessage",
    ]
    form_class = ConfirmationForm
    matomo_pagename = "Persondetaljer - ebokssendview"

    def get_success_url(self):
        return reverse("suila:person_detail", kwargs={"pk": self.object.pk})

    @cached_property
    def type(self):
        return (
            "afventer"
            if settings.ENFORCE_QUARANTINE and self.person_year.in_quarantine
            else "opgørelse"
        )

    @property
    def person_year(self):
        return self.person_month.person_year

    @property
    def person_month(self):
        return (
            PersonMonth.objects.filter(
                person_year__person=self.object,
            )
            .order_by("-person_year__year_id", "-month")
            .first()
        )

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        person_month = (
            PersonMonth.objects.filter(
                person_year__person=self.object,
            )
            .order_by("-person_year__year_id", "-month")
            .first()
        )
        context_data.update(
            {
                "person": self.object,
                "person_month": self.person_month,
                "has_sent": self.object.welcome_letter is not None,
                "type": self.type,
                "existing_pdf": (
                    reverse(
                        "suila:person_existing_message", kwargs={"pk": self.object.pk}
                    )
                    if self.object.welcome_letter
                    else None
                ),
            }
        )
        self.log_view(person_month)
        return context_data

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.cleaned_data["confirmed"]:
            with EboksClient.from_settings() as client:
                suilamessage = SuilaEboksMessage.objects.create(
                    person_month=self.person_month, type=self.type
                )
                suilamessage.send(client)
                suilamessage.update_welcome_letter()
        return super().form_valid(form)


class GraphViewMixin(ContextMixin):
    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["graph_points"] = self.to_json(
            self.calculation_method.graph_points
        )
        return context_data

    @cached_property
    def calculation_method(self):
        year = Year.objects.get(year=self.year)
        return year.calculation_method

    def to_json(self, data: dict) -> str:
        return json.dumps(data, cls=SuilaJSONEncoder)


class GraphView(YearMonthMixin, ViewLogMixin, GraphViewMixin, TemplateView):
    template_name = "suila/graph.html"
    matomo_pagename = "Info - graf"


class PersonGraphView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearMonthMixin,
    ViewLogMixin,
    GraphViewMixin,
    MustHavePersonYearMixin,
    DetailView,
):
    template_name = "suila/graph.html"
    model = Person
    required_object_permissions = ["view"]
    matomo_pagename = "Persondetaljer - graf"

    def get_context_data(self, **kwargs):
        self.log_view(self.object)
        context_data = super().get_context_data(**kwargs)
        yearly_income: Decimal | None = self.get_yearly_income()
        if yearly_income is not None:
            yearly_benefit: Decimal = self.get_yearly_benefit(yearly_income)
            context_data["yearly_income"] = str(yearly_income)
            context_data["yearly_benefit"] = str(yearly_benefit)
        return context_data

    def get_yearly_income(self) -> Decimal | None:
        person: Person = self.get_object()
        try:
            person_month: PersonMonth = PersonMonth.objects.get(
                person_year__person=person,
                person_year__year__year=self.year,
                month=self.month,
            )
        except PersonMonth.DoesNotExist:
            logger.error(
                "No person month for person=%r, year=%r, month=%r",
                person,
                self.year,
                self.month,
            )
            return None
        else:
            return person_month.estimated_year_result

    def get_yearly_benefit(self, yearly_income: Decimal) -> Decimal:
        return ceil(self.calculation_method.calculate(yearly_income))


class CalculatorView(
    LoginRequiredMixin, YearMonthMixin, ViewLogMixin, GraphViewMixin, FormView
):
    form_class = CalculatorForm
    template_name = "suila/calculate.html"
    matomo_pagename = "Info - beregner"

    @cached_property
    def is_advanced(self):
        return self.request.user.has_perm("suila.use_adminsite_calculator_parameters")

    def get_initial(self):
        year_object = Year.objects.get(year=timezone.now().year)
        engine = year_object.calculation_method
        return {
            "calculation_engine": engine,
            "method": engine.__class__.__name__,
        }

    @cached_property
    def engines(self):
        engines = []
        for engine in WorkingTaxCreditCalculationMethod.subclass_instances():
            values = omit(model_to_dict(engine), "id")
            fields = omit(fields_for_model(engine.__class__), "id")
            engines.append(
                {
                    "name": str(engine),
                    "class": engine.__class__.__name__,
                    "fields": {
                        fieldname: {
                            "value": values[fieldname],
                            "label": field.label,
                        }
                        for fieldname, field in fields.items()
                    },
                }
            )
        return engines

    def get_context_data(self, **kwargs):
        self.log_view()
        context_data = super().get_context_data(**kwargs)
        context_data["engines"] = self.engines
        if "graph_points" in kwargs:
            context_data["graph_points"] = kwargs["graph_points"]
        return context_data

    def form_valid(self, form):
        if self.is_advanced:
            method_name = form.cleaned_data["method"]
            method_class = WorkingTaxCreditCalculationMethod.subclasses_by_name()[
                method_name
            ]
            method = method_class(
                **{
                    key: value or Decimal(0)
                    for key, value in form.cleaned_data.items()
                    if key
                    in {
                        "benefit_rate_percent",
                        "personal_allowance",
                        "standard_allowance",
                        "max_benefit",
                        "scaledown_rate_percent",
                        "scaledown_ceiling",
                    }
                }
            )
        else:
            method = self.calculation_method

        result = method.calculate(form.cleaned_data["estimated_year_income"])
        return self.render_to_response(
            self.get_context_data(
                form=form,
                yearly_benefit=str(result),
                monthly_benefit=str(Decimal(result / 12).quantize(Decimal(".01"))),
                graph_points=self.to_json(method.graph_points),
            )
        )


class FormWithFormsetView(FormView):
    formset_class: Any = None

    def get_formset(self, formset_class=None):
        if formset_class is None:
            formset_class = self.get_formset_class()
        return formset_class(**self.get_formset_kwargs())

    def get_formset_kwargs(self):
        """Return the keyword arguments for instantiating the form."""
        kwargs = {
            "initial": self.get_initial(),
            "prefix": self.get_prefix(),
        }
        if self.request.method in ("POST", "PUT"):
            kwargs.update(
                {
                    "data": self.request.POST,
                    "files": self.request.FILES,
                }
            )

        return kwargs

    def get_formset_class(self):
        return self.formset_class

    def get_context_data(self, **kwargs):
        if "formset" not in kwargs:
            kwargs["formset"] = self.get_formset()
        return super().get_context_data(**kwargs)

    def form_valid(self, form, formset):
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, formset):
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = self.get_formset()
        for subform in formset:
            if hasattr(subform, "set_parent_form"):
                subform.set_parent_form(form)  # pragma: no cover
        form.full_clean()
        formset.full_clean()
        if hasattr(form, "clean_with_formset"):
            form.clean_with_formset(formset)  # pragma: no cover
        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form, formset)


class PersonDetailNotesView(
    LoginRequiredMixin,
    PersonYearMonthMixin,
    FormWithFormsetView,
    PermissionsRequiredMixin,
    ViewLogMixin,
    MustHavePersonYearMixin,
    DetailView,
):

    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_notes.html"
    form_class = NoteForm
    formset_class = NoteAttachmentFormSet
    required_model_permissions = [
        "suila.view_note",
    ]
    matomo_pagename = "Persondetaljer - noter"

    def form_valid(  # type: ignore[override]
        self,
        form: NoteForm,
        formset: BaseInlineFormSet,
    ) -> HttpResponse:
        object: Note = form.save(commit=False)
        assert isinstance(self.request.user, User)
        object.author = self.request.user
        object.personyear = self.person_year
        object.save()
        formset.instance = object
        formset.save()
        return super().form_valid(form, formset)

    def get_success_url(self):
        return (
            reverse("suila:person_detail_notes", kwargs={"pk": self.person_pk})
            + "?"
            + urlencode({"year": self.year})
        )

    def get_notes(self) -> QuerySet[Note]:
        return Note.objects.filter(personyear__person_id=self.person_pk).order_by(
            "-created"
        )

    def get_context_data(self, **kwargs):
        notes = self.get_notes()
        self.log_view(notes)
        return super().get_context_data(
            **{
                **kwargs,
                "notes": notes,
            }
        )


class PersonDetailNotesAttachmentView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    MustHavePersonYearMixin,
    BaseDetailView,
):

    model = NoteAttachment
    required_object_permissions = ["view"]

    def get(self, request, *args, **kwargs):
        self.object: NoteAttachment = self.get_object()
        self.log_view(self.object)
        response = HttpResponse(
            self.object.file.read(), content_type=self.object.content_type
        )
        response["Content-Disposition"] = f"attachment; filename={self.object.filename}"
        return response


@method_decorator(xframe_options_sameorigin, name="dispatch")
class GeneratedEboksMessageView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    BaseDetailView,
):
    model = Person
    context_object_name = "person"
    required_model_permissions = ["suila.view_eboksmessage"]

    def get_context_data(self, **kwargs):
        person_month = get_object_or_404(
            PersonMonth,
            person_year__person=self.object,
            person_year__year_id=self.kwargs["year"],
            month=self.kwargs["month"],
        )
        typ = self.kwargs["type"]
        if typ not in ("opgørelse", "afventer"):
            raise Http404
        self.log_view(person_month)
        return super().get_context_data(
            **{
                **kwargs,
                "message": SuilaEboksMessage(person_month=person_month, type=typ),
            }
        )

    def render_to_response(self, context):
        pdf_data = context["message"].pdf
        return HttpResponse(content=pdf_data, content_type="application/pdf")


@method_decorator(xframe_options_sameorigin, name="dispatch")
class EboksMessageView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    BaseDetailView,
):
    model = Person
    context_object_name = "person"
    required_model_permissions = ["suila.view_eboksmessage"]

    def get_context_data(self, **kwargs):
        self.log_view(self.object)
        return super().get_context_data(
            **{**kwargs, "message": self.object.welcome_letter}
        )

    def render_to_response(self, context):
        pdf_data = context["message"].contents
        return HttpResponse(content=pdf_data, content_type="application/pdf")


class PersonPauseUpdateView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    UpdateView,
    FormWithFormsetView,
):
    model = Person
    form_class = PauseForm
    formset_class = NoteAttachmentFormSet
    required_model_permissions = ["suila.change_person"]
    template_name = "suila/forms/pause_form.html"

    @classmethod
    def has_permissions(cls, **kwargs):
        request = kwargs.get("request")
        request_kwargs = kwargs.get("request_kwargs", {})
        user = kwargs.get("user", request.user)
        person = Person.objects.get(pk=int(request_kwargs["pk"]))
        if user.cpr == person.cpr:
            return True if person.allow_pause else False
        return super().has_permissions(**kwargs)

    def get_success_url(self):
        return reverse_lazy("suila:person_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form, formset):
        # We want the object's original state so we can use it for comparison,
        # but at this stage self.object has been tainted with form data, so we need
        # to re-fetch it from the database.
        self.object: Person = self.get_object()
        default_allow_pause = self.object.allow_pause
        default_paused = self.object.paused

        with transaction.atomic():
            user_cpr = getattr(self.request.user, "cpr", None)
            is_citizen = user_cpr is not None and user_cpr == self.object.cpr
            year = form.cleaned_data["year"]
            month = form.cleaned_data["month"]
            note = form.cleaned_data["note"]

            suilamessage = None

            self.object = form.save()
            paused = self.object.paused
            allow_pause = self.object.allow_pause
            pause_reason = self.object.pause_reason

            if paused:
                if is_citizen:
                    standard_note_text = (
                        gettext_noop("Borgeren har sat udbetalinger på pause") + "\n"
                    )
                else:
                    standard_note_text = gettext_noop("Starter udbetalingspause") + "\n"
            else:
                if is_citizen:
                    standard_note_text = (
                        gettext_noop("Borgeren har genoptaget udbetalinger") + "\n"
                    )
                else:
                    standard_note_text = gettext_noop("Stopper udbetalingspause") + "\n"

            if allow_pause and paused:
                standard_note_text += gettext_noop("Borger må genoptage udbetalinger")
            elif allow_pause and not paused:
                standard_note_text += gettext_noop(
                    "Borger må sætte udbetalinger på pause"
                )
            elif not allow_pause and paused:  # pragma: no branch
                standard_note_text += gettext_noop(
                    "Borger må ikke genoptage udbetalinger"
                )

            if pause_reason:
                standard_note_text += "\n"
                with override("da"):
                    standard_note_text += PauseReasonChoices(pause_reason).label

            # Send an eboks message (if person is not allowed to stop the pause himself)
            allow_pause_field_changed = allow_pause != default_allow_pause
            paused_field_changed = paused != default_paused
            if (
                not allow_pause
                and paused
                and (paused_field_changed or allow_pause_field_changed)
                and self.request.user.cpr != self.object.cpr
                and settings.SEND_EBOKS_LETTER_WHEN_PAUSING
            ):
                suilamessage = SuilaEboksMessage.objects.create(
                    person_month=PersonMonth.objects.get(
                        month=month,
                        person_year__year__year=year,
                        person_year__person=self.object,
                    ),
                    type="payout_pause",
                )

                if settings.ENVIRONMENT == "production":
                    with EboksClient.from_settings() as client:
                        suilamessage.send(client)

                suilamessage_filename = f"udbetalingspause_brev_{suilamessage.id}.pdf"
                standard_note_text += "\n"
                standard_note_text += gettext("Eboks besked sendt til borger")

            note_obj = Note.objects.create(
                text=standard_note_text + (("\n" + note) if note else ""),
                personyear=PersonYear.objects.get(person=self.object, year=year),
                author=self.request.user,
            )

            if suilamessage:
                NoteAttachment.objects.create(
                    note=note_obj,
                    file=ContentFile(
                        suilamessage.pdf,
                        name=suilamessage_filename,
                    ),
                    content_type="application/pdf",
                )

            formset.instance = note_obj
            formset.save()

        return super().form_valid(form, formset)


class PersonYearEstimationEngineUpdateView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    UpdateView,
    FormWithFormsetView,
):
    model = PersonYear
    form_class = PersonYearEstimationEngineForm
    formset_class = NoteAttachmentFormSet
    required_model_permissions = ["suila.change_person"]

    def get_success_url(self):
        return reverse_lazy("suila:person_detail", kwargs={"pk": self.object.person.pk})

    def form_valid(self, form, formset):
        preferred_estimation_engine_a = form.cleaned_data[
            "preferred_estimation_engine_a"
        ]
        preferred_estimation_engine_u = form.cleaned_data[
            "preferred_estimation_engine_u"
        ]
        preferred_estimation_engine_a_default = form.cleaned_data[
            "preferred_estimation_engine_a_default"
        ]
        preferred_estimation_engine_u_default = form.cleaned_data[
            "preferred_estimation_engine_u_default"
        ]
        note = form.cleaned_data["note"]
        year = self.object.year.year

        self.object.preferred_estimation_engine_a = preferred_estimation_engine_a
        self.object.preferred_estimation_engine_u = preferred_estimation_engine_u
        self.object.save()

        if preferred_estimation_engine_a_default != preferred_estimation_engine_a:
            engine = preferred_estimation_engine_a
            default_engine = preferred_estimation_engine_a_default
            standard_note_text_a = gettext_noop("A-indkomst estimeringsmotor ændret:")
            standard_note_text_a += f"\n{default_engine} -> {engine}"

        else:
            standard_note_text_a = ""

        if preferred_estimation_engine_u_default != preferred_estimation_engine_u:
            engine = preferred_estimation_engine_u
            default_engine = preferred_estimation_engine_u_default
            standard_note_text_u = gettext_noop("U-indkomst estimeringsmotor ændret:")
            standard_note_text_u += f"\n{default_engine} -> {engine}"
        else:
            standard_note_text_u = ""

        note_text = "\n".join(
            [t for t in [standard_note_text_a, standard_note_text_u, note] if t]
        )

        note_obj = Note.objects.create(
            text=note_text,
            personyear=PersonYear.objects.get(person=self.object.person, year=year),
            author=self.request.user,
        )

        formset.instance = note_obj
        formset.save()
        return super().form_valid(form, formset)


class PersonAnnualIncomeEstimateUpdateView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    UpdateView,
    FormWithFormsetView,
):
    model = Person
    form_class = PersonAnnualIncomeEstimateForm
    formset_class = NoteAttachmentFormSet
    required_model_permissions = ["suila.change_person"]

    def get_success_url(self):
        return reverse_lazy("suila:person_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form, formset):
        year = form.cleaned_data["year"]
        month = form.cleaned_data["month"]
        note = form.cleaned_data["note"]
        annual_income_estimate = form.cleaned_data["annual_income_estimate"]

        self.object.annual_income_estimate = annual_income_estimate
        self.object.save()

        try:
            person_month = PersonMonth.objects.get(
                month=month,
                person_year__year__year=year,
                person_year__person__id=self.object.id,
            )
        except PersonMonth.DoesNotExist:
            person_month = None

        # Recalculate current and all future months for this user
        while person_month is not None:
            try:
                prisme_batch_item = person_month.prismebatchitem
            except PersonMonth.prismebatchitem.RelatedObjectDoesNotExist:
                prisme_batch_item = None

            # Only recalculate if this month was not sent to Prisme
            if not prisme_batch_item:
                call_command(
                    ManagementCommands.CALCULATE_BENEFIT,
                    person_month.person_year.year,
                    person_month.month,
                    cpr=self.object.cpr,
                )
            person_month = person_month.next

        if annual_income_estimate:
            annual_income_estimate_formatted = number_format(
                annual_income_estimate,
                use_l10n=True,
                force_grouping=True,
            )
            standard_note_text = gettext_noop("Benyt manuelt estimeret årsindkomst")
            standard_note_text += f"\n({annual_income_estimate_formatted} kr.)"
        else:
            standard_note_text = gettext_noop("Benyt automatisk estimeret årsindkomst")

        note_obj = Note.objects.create(
            text=standard_note_text + "\n" + note,
            personyear=PersonYear.objects.get(person=self.object, year=year),
            author=self.request.user,
        )

        formset.instance = note_obj
        formset.save()

        return super().form_valid(form, formset)


class TaxScopeHistoryTable(Table):
    tax_scope = TemplateColumn(
        accessor=Accessor("_tax_scope"),
        template_name="suila/table_columns/tax_scope.html",
        verbose_name=_("Status"),
    )
    year = Column(
        accessor=Accessor("_year"),
        verbose_name=_("År"),
    )
    start_date = TemplateColumn(
        accessor=Accessor("_start_date"),
        template_name="suila/table_columns/full_date.html",
        verbose_name=_("Startdato"),
    )
    end_date = TemplateColumn(
        accessor=Accessor("_end_date"),
        template_name="suila/table_columns/full_date.html",
        verbose_name=_("Slutdato"),
    )


class PersonTaxScopeHistoryView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    SingleTableMixin,
    DetailView,
):
    paginate_by = 5
    model = Person
    context_object_name = "person"
    attributes_to_show = ["tax_scope"]
    template_name = "suila/person_tax_scope_history.html"

    table_class = TaxScopeHistoryTable
    required_model_permissions = ["suila.view_person"]

    def get_table_data(self):
        person: Person = self.object
        person_years: QuerySet[PersonYear] = person.personyear_set.order_by(
            "-year__year",
            "-taxinformationperiod__start_date",
        ).annotate(
            # Prefix using underscore to avoid name collision on `year` and `tax_scope`
            _year=F("year__year"),
            _tax_scope=F("taxinformationperiod__tax_scope"),
            _start_date=F("taxinformationperiod__start_date"),
            _end_date=F("taxinformationperiod__end_date"),
        )
        return person_years

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person_pk"] = self.kwargs["pk"]
        self.log_view()
        return context


class CalculationParametersListView(
    LoginRequiredMixin, PermissionsRequiredMixin, ListView, FormView
):
    model = Year
    template_name = "suila/calculation_parameters_list.html"
    form_class = CalculationParametersForm
    success_url = reverse_lazy("suila:calculation_parameters_list")
    required_model_permissions = [
        "suila.view_standardworkbenefitcalculationmethod",
        "suila.add_standardworkbenefitcalculationmethod",
        "suila.change_standardworkbenefitcalculationmethod",
        "suila.view_year",
        "suila.change_year",
    ]

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        return super().post(request, *args, **kwargs)

    @staticmethod
    def next_year():
        return CalculationParametersListView.this_year() + 1

    @staticmethod
    def this_year():
        return date.today().year

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(year__range=(2025, self.this_year()))
            .order_by("-year")
        )

    def get_initial(self):
        year, _ = Year.objects.get_or_create(year=self.next_year())
        method = year.calculation_method
        if method is not None:
            return model_to_dict(method)
        return None

    def get_context_data(self, **kwargs):
        methods = set(
            filter(None, [year.calculation_method for year in self.get_queryset()])
        )
        return super().get_context_data(
            **{
                **kwargs,
                "graph_points": json.dumps(
                    {method.pk: method.graph_points for method in methods},
                    cls=SuilaJSONEncoder,
                ),
            }
        )

    def form_valid(self, form):
        year, year_created = Year.objects.get_or_create(year=self.next_year())
        method = year.calculation_method
        create = False
        if method is None:
            create = True
            method = StandardWorkBenefitCalculationMethod()
        for key, value in form.cleaned_data.items():
            if hasattr(method, key):  # pragma: no branch
                setattr(method, key, value)
        method.save()
        if create:
            year.calculation_method = method
            year.save()
        messages.add_message(
            self.request, messages.SUCCESS, _("Beregningsparametrene blev opdateret")
        )
        return super().form_valid(form)


class CalculationParametersGraph(BaseGetFormView):
    form_class = CalculationParametersForm

    def form_valid(self, form):
        method = StandardWorkBenefitCalculationMethod()
        for key, value in form.cleaned_data.items():
            if hasattr(method, key):  # pragma: no branch
                setattr(method, key, value)
        return JsonResponse(
            data={"points": method.graph_points}, encoder=SuilaJSONEncoder
        )

    def form_invalid(self, form):
        return JsonResponse(data={"errors": form.errors.get_json_data()}, status=400)
