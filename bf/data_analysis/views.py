# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import copy
import dataclasses
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import List
from urllib.parse import urlencode

from data_analysis.forms import (
    HistogramOptionsForm,
    PersonAnalysisOptionsForm,
    PersonYearListOptionsForm,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, F, Model, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic import DetailView, FormView
from django.views.generic.list import ListView
from project.util import params_no_none, strtobool

from bf.data import engine_keys
from bf.estimation import EstimationEngine
from bf.models import (
    IncomeType,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
    Year,
)
from bf.simulation import Simulation


class SimulationJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Model):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        if isinstance(obj, EstimationEngine):
            return {
                "class": obj.__class__.__name__,
                "description": obj.description,
            }
        if isinstance(obj, Simulation):
            return {
                "person": obj.person,
                "year": obj.year,
                "rows": obj.result.rows,
            }

        return super().default(obj)


class PersonAnalysisView(LoginRequiredMixin, DetailView, FormView):
    model = Person
    context_object_name = "person"
    template_name = "data_analysis/person_analysis.html"
    form_class = PersonAnalysisOptionsForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.year = self.kwargs["year"]
        self.income_type = IncomeType.A
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        self.income_type = IncomeType(form.cleaned_data["income_type"] or "A")
        return self.render_to_response(
            self.get_context_data(object=self.object, form=form)
        )

    def get_context_data(self, form=None, **kwargs):
        if form is not None and form.is_valid():
            simulation = Simulation(
                EstimationEngine.instances(),
                self.get_object(),
                year=self.year,
                income_type=self.income_type,
            )
            chart_data = json.dumps(simulation, cls=SimulationJSONEncoder)
        else:
            chart_data = "{}"
        return super().get_context_data(
            **{
                **kwargs,
                "year_urls": {
                    py.year.year: reverse(
                        "data_analysis:person_analysis",
                        kwargs={"year": py.year.year, "pk": self.object.pk},
                    )
                    for py in self.object.personyear_set.all()
                },
                "chart_data": chart_data,
            }
        )

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "data": {**self.request.GET.dict(), "year": self.year},
            "instance": self.object,
        }


class PersonYearEstimationMixin:

    def get_queryset(self):
        qs = PersonYear.objects.filter(year=self.year).select_related("person")

        form = self.get_form()
        if form.is_valid():

            a_income = form.cleaned_data["has_a"]
            if a_income not in (None, ""):
                qs = qs.annotate(a_count=Count("personmonth__monthlyaincomereport"))
                if strtobool(a_income):
                    qs = qs.filter(a_count__gt=0)
                else:
                    qs = qs.filter(a_count=0)

            b_income = form.cleaned_data["has_b"]
            if b_income not in (None, ""):
                qs = qs.annotate(b_count=Count("personmonth__monthlybincomereport"))
                if strtobool(b_income):
                    qs = qs.filter(b_count__gt=0)
                else:
                    qs = qs.filter(b_count=0)

        for engine in engine_keys:
            for income_type in IncomeType:
                qs = qs.annotate(
                    **{
                        f"{engine}_mean_error_{income_type}": Subquery(
                            PersonYearEstimateSummary.objects.filter(
                                person_year=OuterRef("pk"),
                                estimation_engine=engine,
                                income_type=income_type,
                            ).values("mean_error_percent")
                        ),
                        f"{engine}_rmse_{income_type}": Subquery(
                            PersonYearEstimateSummary.objects.filter(
                                person_year=OuterRef("pk"),
                                estimation_engine=engine,
                                income_type=income_type,
                            ).values("rmse_percent")
                        ),
                    }
                )

        # Originally this annotated on the sum of
        # personmonth__monthlyaincomereport__amount, but that produced weird
        # results in other annotations, such as Sum("personmonth__benefit_paid")
        # including two months twice for a few PersonYears
        # Probably
        # https://docs.djangoproject.com/en/5.0/topics/db/aggregation/#combining-multiple-aggregations
        # Therefore we introduce this field instead, which is also quicker to sum over
        qs = qs.annotate(
            actual_sum=Coalesce(Sum("personmonth__amount_sum"), Decimal(0))
        )

        qs = qs.annotate(payout=Sum("personmonth__benefit_paid"))

        qs = qs.annotate(
            correct_payout=Subquery(
                PersonMonth.objects.filter(person_year=OuterRef("pk"))
                .order_by("-month")
                .values("actual_year_benefit")[:1]
            )
        )
        qs = qs.annotate(payout_offset=F("payout") - F("correct_payout"))

        if form.is_valid():
            selected_model = form.cleaned_data.get("selected_model", None)
            min_offset = form.cleaned_data.get("min_offset", None)
            max_offset = form.cleaned_data.get("max_offset", None)

            if selected_model:
                if min_offset is not None:
                    qs = qs.filter(**{f"{selected_model}__gte": min_offset})
                if max_offset is not None:
                    qs = qs.filter(**{f"{selected_model}__lte": max_offset})

        qs = qs.annotate(
            preferred_estimation_engine_a=F("person__preferred_estimation_engine_a"),
            preferred_estimation_engine_b=F("person__preferred_estimation_engine_b"),
        )

        return qs

    @property
    def year(self):
        return self.kwargs["year"]


class PersonListView(PersonYearEstimationMixin, LoginRequiredMixin, ListView, FormView):
    paginate_by = 30
    model = PersonYear
    template_name = "data_analysis/personyear_list.html"
    form_class = PersonYearListOptionsForm
    default_ordering = "person__cpr"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object_list = None

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "data": self.request.GET}

    def get_ordering(self) -> List[str]:
        ordering = self.request.GET.get("order_by") or self.default_ordering
        return ordering.split(",")

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.order_by(*self.get_ordering())
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year

        form = context["form"]
        form.full_clean()
        params = params_no_none(form.cleaned_data)
        current_order_by = params.pop("order_by", None) or self.default_ordering
        params["page"] = context["page_obj"].number
        sort_params = {}
        for value, label in form.fields["order_by"].choices:
            order_by = value if value != current_order_by else ("-" + value)
            sort_params[value] = urlencode({**params, "order_by": order_by})
        context["sort_params"] = sort_params
        context["order_current"] = current_order_by

        return context


class HistogramView(LoginRequiredMixin, PersonYearEstimationMixin, FormView):
    template_name = "data_analysis/histogram.html"
    form_class = HistogramOptionsForm

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") == "json":
            return HttpResponse(
                json.dumps(self.get_histogram(), cls=DjangoJSONEncoder),
                content_type="application/json",
            )
        return super().get(request, *args, **kwargs)  # pragma: no cover

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Make `data` a mutable dict, as we need to update it below
        kwargs["data"] = copy.copy(self.request.GET)
        # Set resolution to 10% if not provided by GET parameters
        kwargs["data"].setdefault("resolution", "10")
        # Set metric to ME if not provided by GET parameters
        kwargs["data"].setdefault("metric", "mean_error")
        # Get the initial value (URL) for the `year` form field.
        # Since this form is bound, we need to pass the initial value via
        # the `data` form kwarg.
        year = Year.objects.get(year=self.kwargs["year"])
        year_url = self.form_class().get_year_url(year)
        kwargs["data"]["year"] = year_url
        kwargs["data"]["year_val"] = year
        return kwargs

    def get_resolution(self):
        form = self.get_form()
        if form.is_valid():
            return int(form.cleaned_data["resolution"])
        return 10

    def get_metric(self):
        form = self.get_form()
        if form.is_valid():
            return form.cleaned_data["metric"]
        return "mean_error"

    def get_income_type(self):
        form = self.get_form()
        if form.is_valid():
            return form.cleaned_data.get("income_type") or IncomeType.A
        return IncomeType.A

    def get_resolution_label(self):
        metric = self.get_resolution()
        form = self.get_form()
        return dict(form.fields["resolution"].choices)[metric]

    def get_histogram(self) -> dict:
        resolution = self.get_resolution()
        metric = self.get_metric()
        income_type = self.get_income_type()
        observations: defaultdict = defaultdict(Counter)
        person_years = self.get_queryset()
        half_resolution = Decimal(resolution / 2)

        keys = (metric,) if metric == "payout_offset" else engine_keys

        for key in keys:
            for item in person_years:
                if key in engine_keys:
                    val = getattr(item, f"{key}_{metric}_{income_type}", None)
                else:
                    val = getattr(item, metric, None)

                if val is not None:
                    # Bucket 0 contains values between -5 and 5
                    # Bucket 10 contains values between 5 and 15
                    # And so on
                    sign = -1 if val < 0 else 1
                    centered_val = (abs(val) + half_resolution) * sign
                    bucket = int(resolution * (centered_val // resolution))
                    observations[key][bucket] += 1

        for counter in observations.values():
            for bucket in range(0, 100, resolution):
                if bucket not in counter:
                    counter[bucket] = 0

        resolution_label = self.get_resolution_label()
        unit = "%" if "%" in resolution_label else "kr"

        return {"data": observations, "resolution": resolution, "unit": unit}
