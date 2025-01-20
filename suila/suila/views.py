# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools
import json
from functools import cached_property
from typing import Callable
from urllib.parse import urlencode

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import CharField, Count, F, Field, Q, QuerySet, Sum, Value
from django.db.models.functions import Cast, LPad
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, TemplateView
from django.views.generic.detail import BaseDetailView
from django_filters import CharFilter, ChoiceFilter, FilterSet
from django_filters.views import FilterView
from django_tables2 import Column, SingleTableMixin, Table
from django_tables2.columns.linkcolumn import BaseLinkColumn
from django_tables2.utils import Accessor
from login.view_mixins import LoginRequiredMixin

from suila.forms import NoteAttachmentFormSet, NoteForm
from suila.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyIncomeReport,
    Note,
    NoteAttachment,
    Person,
    PersonMonth,
    PersonYear,
)
from suila.querysets import PersonKeyFigureQuerySet
from suila.templatetags.date_tags import month_name
from suila.view_mixins import FormWithFormsetView


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "suila/root.html"


class CPRColumn(BaseLinkColumn):
    def __init__(self, *args, **kwargs):
        linkify = dict(viewname="suila:person_detail", args=[Accessor("pk")])
        kwargs.setdefault("verbose_name", _("CPR-nummer"))
        kwargs.setdefault("linkify", linkify)
        super().__init__(*args, **kwargs)


class PersonTable(Table):
    cpr = CPRColumn(accessor=Accessor("_cpr"), order_by=Accessor("_cpr"))
    name = Column(verbose_name=_("Navn"))
    full_address = Column(verbose_name=_("Adresse"))
    civil_state = Column(verbose_name=_("Civilstand"))
    location_code = Column(verbose_name=_("Stedkode"))
    total_estimated_year_result = Column(
        accessor=Accessor("_total_estimated_year_result"),
        order_by=Accessor("_total_estimated_year_result"),
        verbose_name=_("Forventet samlet indtægt i indeværende år"),
    )
    total_actual_year_result = Column(
        accessor=Accessor("_total_actual_year_result"),
        order_by=Accessor("_total_actual_year_result"),
        verbose_name=_("Faktisk samlet indtægt i indeværende år"),
    )
    benefit_paid = Column(
        accessor=Accessor("_benefit_paid"),
        order_by=Accessor("_benefit_paid"),
        verbose_name=_("Beskæftigelsesfradrag til dato i indeværende år"),
    )


class CategoryChoiceFilter(ChoiceFilter):
    _isnull = "isnull"

    def __init__(self, *args, **kwargs):
        field = kwargs.pop("field")
        super().__init__(*args, choices=self._get_choices(field.field), **kwargs)

    def filter(self, qs, value):
        if value == self._isnull:
            return self.get_method(qs)(**{"%s__isnull" % self.field_name: True})
        return super().filter(qs, value)  # pragma: no cover

    def _get_choices(self, field: Field) -> Callable:
        def _func():
            return [
                (
                    val[field.name] or self._isnull,
                    f"{val[field.name] or _('Ingen')} ({val['count']})",
                )
                for val in field.model.objects.values(field.name)
                .annotate(count=Count("id"))
                .order_by(field.name)
            ]

        return _func


class PersonFilterSet(FilterSet):
    cpr = CharFilter("_cpr", label=_("CPR-nummer"))
    name = CharFilter("name", lookup_expr="icontains", label=_("Navn"))
    full_address = CharFilter(
        "full_address", lookup_expr="icontains", label=_("Adresse")
    )
    civil_state = CategoryChoiceFilter(field=Person.civil_state, label=_("Civilstand"))
    location_code = CategoryChoiceFilter(
        field=Person.location_code, label=_("Stedkode")
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
        return PersonYear.objects.get(year_id=self.year, person_id=self.person_pk)


class ChartMixin:
    def get_month_names(self) -> list[str]:
        return [month_name(month) for month in range(1, 13)]

    def to_json(self, obj: dict) -> str:
        return json.dumps(obj, cls=DjangoJSONEncoder)


class PersonKeyFigureViewMixin(PersonYearMonthMixin):
    def get_key_figure_queryset(self) -> PersonKeyFigureQuerySet:
        # Get "key figure" queryset for current year and month
        qs = PersonKeyFigureQuerySet.from_queryset(
            super().get_queryset(),  # type: ignore[misc]
            year=self.year,
            month=self.month,
        )
        return qs


class PersonSearchView(
    LoginRequiredMixin, PersonKeyFigureViewMixin, SingleTableMixin, FilterView
):
    model = Person
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "suila/person_search.html"

    def get_queryset(self):
        qs = self.get_key_figure_queryset()
        # Add zero-padded text version of CPR to ensure proper display and sorting
        qs = qs.annotate(_cpr=LPad(Cast("cpr", CharField()), 10, Value("0")))
        # Set initial sorting (can be overridden by user)
        qs = qs.order_by("_cpr")
        return qs


class PersonDetailView(LoginRequiredMixin, PersonKeyFigureViewMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail.html"

    def get_queryset(self):
        return self.get_key_figure_queryset()

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        # Add key figures as separate context variables
        for annotation in (
            "_total_estimated_year_result",
            "_total_actual_year_result",
            "_benefit_paid",
        ):
            # Strip leading underscore, which is not allowed in Django templates
            context_data[annotation[1:]] = getattr(self.object, annotation)

        return context_data


class PersonDetailBenefitView(
    LoginRequiredMixin, PersonYearMonthMixin, ChartMixin, DetailView
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_benefits.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        # Add table data: benefits per month
        context_data["benefit_data"] = self.get_benefit_data()
        # Add chart data: benefit chart
        context_data["benefit_chart"] = self.to_json(self.get_benefit_chart())

        return context_data

    def get_benefit_data(self):
        benefit_series = self.get_benefit_series()
        estimate_series = self.get_estimated_yearly_income_series()
        return [
            {
                "benefit": benefit,
                "estimate": estimate,
            }
            for benefit, estimate in zip(
                benefit_series["data"], estimate_series["data"]
            )
        ]

    def get_benefit_chart(self) -> dict:
        return {
            "chart": {
                "type": "line",
                "height": 600,
                "animations": {"enabled": False},
            },
            "series": self.get_all_benefit_chart_series(),
            "xaxis": {
                "type": "category",
                "categories": self.get_month_names(),
            },
            "yaxis": [
                {
                    "group": "benefit",
                    "seriesName": _("Beregnet beskæftigelsesfradrag"),
                    "type": "numeric",
                    "min": 0,
                    "axisBorder": {"show": True, "color": "#00E396"},
                    "labels": {"style": {"colors": "#00E396"}},
                },
                {
                    "group": "estimated_total_income",
                    "seriesName": _("Estimeret total årsindkomst"),
                    "type": "numeric",
                    "opposite": True,
                    "axisBorder": {"show": True, "color": "#008FFB"},
                    "labels": {"style": {"colors": "#008FFB"}},
                },
            ],
            "dataLabels": {"enabled": True},
            "legend": {"show": True, "position": "left"},
        }

    def get_all_benefit_chart_series(self) -> list[dict]:
        return [self.get_benefit_series(), self.get_estimated_yearly_income_series()]

    def get_benefit_series(self) -> dict:
        # Calculated benefit (based on monthly A and B income sums)
        benefits = PersonMonth.objects.filter(
            person_year__person=self.object,
            person_year__year__year=self.year,
        ).order_by("month")
        return {
            "data": [
                float(val) if val is not None else 0
                for val in benefits.values_list("benefit_paid", flat=True)
            ],
            "name": _("Beregnet beskæftigelsesfradrag"),
            "group": "benefit",
        }

    def get_estimated_yearly_income_series(self) -> dict:
        # Estimated total yearly income for each month
        estimates = (
            IncomeEstimate.objects.filter(
                Q(
                    Q(
                        engine=F(
                            "person_month__person_year__preferred_estimation_engine_a"
                        ),
                        income_type=IncomeType.A,
                    )
                    | Q(
                        engine=F(
                            "person_month__person_year__preferred_estimation_engine_b"
                        ),
                        income_type=IncomeType.B,
                    )
                ),
                person_month__person_year__person=self.object,
                person_month__person_year__year__year=self.year,
            )
            .order_by("person_month__month")
            .values("person_month__month")
            .annotate(
                _total_estimated_year_result=Sum("estimated_year_result"),
            )
        )
        return {
            "data": [
                float(val) if val is not None else 0
                for val in estimates.values_list(
                    "_total_estimated_year_result", flat=True
                )
            ],
            "name": _("Estimeret samlet lønindkomst"),
            "group": "estimated_total_income",
            "type": "column",
        }


class PersonDetailIncomeView(
    LoginRequiredMixin, YearMonthMixin, ChartMixin, DetailView
):
    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_income.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        # Add table data: *total* income per employer and type (A and B)
        context_data["income_per_employer_and_type"] = (
            self.get_income_per_employer_and_type()
        )
        # Add table data: income per employer and type
        context_data["income_data"] = self.get_income_chart_series()
        # Add chart data: income chart (same data as "income per employer and type")
        context_data["income_chart"] = self.to_json(self.get_income_chart())

        return context_data

    def get_income_chart_series(self) -> list[dict]:
        result: list[dict] = []

        # All income data (A and B, separate series for each employer/trader)
        for name, data in self.get_income_by_source():
            result.append(
                {
                    "data": data,
                    "name": name,
                    "group": "income",
                    "type": "column",
                }
            )

        return result

    def get_income_chart(self) -> dict:
        return {
            "chart": {
                "type": "bar",
                "stacked": True,
                "height": 600,
                "animations": {"enabled": False},
            },
            "series": self.get_income_chart_series(),
            "xaxis": {
                "type": "category",
                "categories": self.get_month_names(),
            },
            "yaxis": [
                {
                    "group": "income",
                    "seriesName": [
                        series["name"] for series in self.get_income_chart_series()
                    ],
                    "type": "numeric",
                },
            ],
            "plotOptions": {
                # Show totals for each month
                "bar": {"dataLabels": {"total": {"enabled": True}}}
            },
            "dataLabels": {"enabled": True},
            "legend": {"show": True, "position": "left"},
        }

    def get_income_per_employer_and_type(self) -> list[dict]:
        qs = (
            MonthlyIncomeReport.objects.filter(
                person_month__person_year__person=self.object,
                person_month__person_year__year__year=self.year,
            )
            .values("year")  # TODO: use employer as group-by key when we have it
            .annotate(
                total_a_income=Sum("a_income"),
                total_b_income=Sum("b_income"),
            )
        )

        return [
            # TODO: yield a row for each employer when we have it
            {
                "source": _("A-indkomst") if field == "a_income" else _("B-indkomst"),
                "total_amount": row[f"total_{field}"],
            }
            for field, row in itertools.product(["a_income", "b_income"], qs)
        ]

    def get_income_by_source(self):
        def zero_pad(qs: QuerySet, field: str) -> list[int]:
            by_month = {row["month"]: row[field] for row in qs}
            return [by_month.get(month, 0) for month in range(1, 13)]

        qs = (
            MonthlyIncomeReport.objects.filter(
                person_month__person_year__person=self.object, year=self.year
            )
            .values("month")  # TODO: use employer as group-by key when we have it
            .annotate(
                _a_income=Sum("a_income"),
                _b_income=Sum("b_income"),
            )
            .order_by("month")
        )

        # TODO: yield a row for each employer when we have it
        yield _("A-indkomst"), zero_pad(qs, "_a_income")
        yield _("B-indkomst"), zero_pad(qs, "_b_income")


class PersonDetailNotesView(
    LoginRequiredMixin, PersonYearMonthMixin, FormWithFormsetView, DetailView
):

    model = Person
    context_object_name = "person"
    template_name = "suila/person_detail_notes.html"
    form_class = NoteForm
    formset_class = NoteAttachmentFormSet

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def form_valid(
        self,
        form: NoteForm,
        formset: BaseInlineFormSet,
    ) -> HttpResponse:  # type: ignore[override]
        object: Note = form.save(commit=False)
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
        return Note.objects.filter(
            personyear__year_id=self.year, personyear__person_id=self.person_pk
        ).order_by("created")

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "notes": self.get_notes(),
            }
        )


class PersonDetailNotesAttachmentView(LoginRequiredMixin, BaseDetailView):

    # TODO: adgangskontrol
    model = NoteAttachment

    def get(self, request, *args, **kwargs):
        self.object: NoteAttachment = self.get_object()
        response = HttpResponse(
            self.object.file.read(), content_type=self.object.content_type
        )
        response["Content-Disposition"] = f"attachment; filename={self.object.filename}"
        return response
