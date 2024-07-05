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
from data_analysis.models import PersonYearEstimateSummary
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Model, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.views.generic import FormView, UpdateView
from django.views.generic.list import ListView
from project.util import strtobool

from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import Person, PersonYear, Year
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


class PersonAnalysisView(LoginRequiredMixin, UpdateView):
    model = Person
    context_object_name = "person"
    template_name = "data_analysis/person_analysis.html"
    form_class = PersonAnalysisOptionsForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.year = self.kwargs["year"]
        self.simulation = Simulation(
            [InYearExtrapolationEngine(), TwelveMonthsSummationEngine()],
            self.get_object(),
            year=self.year,
        )

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") == "json":
            return HttpResponse(
                json.dumps(self.simulation, cls=SimulationJSONEncoder),
                content_type="application/json",
            )
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["year"] = self.year
        return kwargs


class PersonYearEstimationMixin:

    def get_queryset(self):
        qs = PersonYear.objects.filter(year=self.year, person__cpr=16013)

        # form = self.get_form()
        # if form.is_valid():
        #
        #     a_income = form.cleaned_data["has_a"]
        #     if a_income not in (None, ""):
        #         qs = qs.annotate(a_count=Count("personmonth__monthlyaincomereport"))
        #         if strtobool(a_income):
        #             qs = qs.filter(a_count__gt=0)
        #         else:
        #             qs = qs.filter(a_count=0)
        #
        #     b_income = form.cleaned_data["has_b"]
        #     if b_income not in (None, ""):
        #         qs = qs.annotate(b_count=Count("personmonth__monthlybincomereport"))
        #         if strtobool(b_income):
        #             qs = qs.filter(b_count__gt=0)
        #         else:
        #             qs = qs.filter(b_count=0)
        #
        # for engine in ("InYearExtrapolationEngine", "TwelveMonthsSummationEngine"):
        #     qs = qs.annotate(
        #         **{
        #             engine: Subquery(
        #                 PersonYearEstimateSummary.objects.filter(
        #                     person_year=OuterRef("pk"), estimation_engine=engine
        #                 ).values("offset_percent")
        #             )
        #         }
        #     )

        qs = qs.annotate(
            actual_sum=
                Sum("personmonth__monthlyaincomereport__amount")
            #
            # +
            #     Sum("personmonth__monthlybincomereport__amount")

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
        qs = super().get_queryset().select_related("person")

        # `None` is an accepted value here, when benefits have not been calculated yet
        qs = qs.annotate(payout=Sum("personmonth__benefit_paid"))
        qs = qs.annotate(count=Count("personmonth__pk"))
        for x in qs:
            print(x.count)
            for m in x.personmonth_set.order_by("month"):
                print(m)

        qs = qs.order_by(*self.get_ordering())
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year

        form = context["form"]
        form.full_clean()
        params = copy.copy(form.cleaned_data)
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
        # Get the initial value (URL) for the `year` form field.
        # Since this form is bound, we need to pass the initial value via
        # the `data` form kwarg.
        year_initial_value = self.form_class().get_year_url(
            Year.objects.get(year=self.kwargs["year"])
        )
        kwargs["data"]["year"] = year_initial_value
        return kwargs

    def get_percentile_size(self):
        form = self.get_form()
        if form.is_valid():
            return int(form.cleaned_data["resolution"])
        return 10

    def get_histogram(self) -> dict:
        percentile_size = self.get_percentile_size()
        observations: defaultdict = defaultdict(Counter)
        person_years = self.get_queryset()

        for item in person_years:
            for key in ("InYearExtrapolationEngine", "TwelveMonthsSummationEngine"):
                val = getattr(item, key, None)
                if val is not None:
                    bucket = int(percentile_size * (val // percentile_size))
                    observations[key][bucket] += 1

        for counter in observations.values():
            for bucket in range(0, 100, percentile_size):
                if bucket not in counter:
                    counter[bucket] = 0

        return {"data": observations, "percentile_size": percentile_size}
