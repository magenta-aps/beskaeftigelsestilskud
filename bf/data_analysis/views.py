# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import dataclasses
import json
from collections import Counter, defaultdict
from decimal import Decimal

from data_analysis.forms import HistogramOptionsForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    Model,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Abs
from django.http import HttpResponse
from django.views.generic import DetailView, FormView
from django.views.generic.list import ListView

from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import Person, PersonYear
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


class PersonAnalysisView(LoginRequiredMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "data_analysis/person_analysis.html"

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


class PersonYearEstimationMixin:
    def _add_predictions(self, person_years) -> QuerySet[PersonYear]:
        # Use the DB to calculate offset in percent between the actual and the
        # estimated yearly income.
        # (This produces a "values queryset" with >1 row per person year, as each
        # person year will usually have predictions made by two engines.)
        qs = (
            # person_years may be subject to offset & limit,
            # which would bleed into qs if we just use that queryset
            PersonYear.objects.filter(pk__in=person_years)
            .prefetch_related("personmonth_set__incomeestimate_set")
            .values("pk", "personmonth__incomeestimate__engine")
            .annotate(
                num=Count("personmonth__incomeestimate__id"),
                sum=Sum(
                    Abs(
                        F("personmonth__incomeestimate__actual_year_result")
                        - F("personmonth__incomeestimate__estimated_year_result")
                    )
                ),
            )
            .annotate(
                offset_pct=Case(
                    When(
                        personmonth__incomeestimate__actual_year_result=0,
                        then=Value(0),
                    ),
                    default=(
                        Value(100)
                        * F("sum")
                        / F("personmonth__incomeestimate__actual_year_result")
                        / F("num")
                    ),
                    output_field=DecimalField(),
                ),
            )
        )

        # Transform the queryset into a dict mapping `PersonYear` PKs to dictionaries
        # containing "InYearExtrapolationEngine" and "TwelveMonthsSummationEngine" keys.
        qs_dict: defaultdict = defaultdict(dict)
        for row in qs:
            pk = row["pk"]
            engine = row["personmonth__incomeestimate__engine"]
            qs_dict[pk][engine] = row["offset_pct"]

        # Add "InYearExtrapolationEngine" and "TwelveMonthsSummationEngine" attributes
        # to all `PersonYear` instances passed in `person_years`.
        # This keeps the new implementation identical to the former implementation.
        for person_year in person_years:
            data = qs_dict[person_year.pk]
            for key in ("InYearExtrapolationEngine", "TwelveMonthsSummationEngine"):
                val = data.get(key, Decimal("0"))
                setattr(person_year, key, val)

        return person_years


class PersonListView(PersonYearEstimationMixin, LoginRequiredMixin, ListView):
    paginate_by = 30
    model = PersonYear
    template_name = "data_analysis/personyear_list.html"

    @property
    def year(self):
        return self.kwargs["year"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object_list = None

    def get_queryset(self):
        return (
            PersonYear.objects.filter(year=self.year)
            .select_related("person")
            .order_by("person__cpr")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year
        self.object_list = self._add_predictions(context["object_list"])
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
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["data"] = self.request.GET
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["resolution"] = self.request.GET.get("resolution", 10)
        return initial

    def get_percentile_size(self):
        form = self.get_form()
        if form.is_valid():
            return form.cleaned_data["resolution"]
        return 10

    def get_histogram(self) -> dict:
        percentile_size = self.get_percentile_size()
        observations: defaultdict = defaultdict(Counter)
        person_years = self._add_predictions(
            PersonYear.objects.filter(year=self.kwargs["year"])
        )

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
