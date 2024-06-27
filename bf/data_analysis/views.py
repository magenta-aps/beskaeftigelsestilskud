# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import dataclasses
import json
from decimal import Decimal
from typing import Dict, List

from data_analysis.models import CalculationResult
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model
from django.http import HttpResponse
from django.views.generic import DetailView
from django.views.generic.list import ListView
from project.util import group

from bf.calculate import (
    CalculationEngine,
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
        if isinstance(obj, CalculationEngine):
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


class PersonListView(LoginRequiredMixin, ListView):
    paginate_by = 30
    model = PersonYear
    template_name = "data_analysis/personyear_list.html"

    @property
    def year(self):
        return self.kwargs["year"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object_list = None

    #
    # def get(self, request, *args, **kwargs):
    #     if request.GET.get("format") == "json":
    #         return HttpResponse(
    #             json.dumps(self.get_histogram(), cls=DjangoJSONEncoder),
    #             content_type="application/json",
    #         )
    #     return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (
            PersonYear.objects.filter(year=self.year)
            .select_related("person")
            .order_by("person__cpr")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year
        person_years = self.object_list = context["object_list"]
        qs = CalculationResult.annotate_person_year(
            CalculationResult.objects.all()
        ).filter(f_person_year__in=person_years)
        calculation_results: Dict[int, List[CalculationResult]] = group(
            qs, "f_person_year"
        )
        for person_year in person_years:
            actual_sum = person_year.sum_amount
            person_calculation_results = group(
                calculation_results[person_year.pk], "engine"
            )
            if person_calculation_results and actual_sum:
                for engine, engine_calculations in person_calculation_results.items():
                    engine_offset_pct = (
                        100
                        * sum(
                            [
                                engine_calculation.absdiff
                                for engine_calculation in engine_calculations
                            ]
                        )
                        / actual_sum
                        / len(engine_calculations)
                    )
                    setattr(person_year, engine, engine_offset_pct)
            else:
                person_year.InYearExtrapolationEngine = Decimal(0)
                person_year.TwelveMonthsSummationEngine = Decimal(0)
        self.context_data = context
        return context

    # def get_histogram(self) -> defaultdict:
    #     percentile_size = 10
    #     observations: defaultdict = defaultdict(Counter)
    #     for item in self.object_list:
    #         for key in ("InYearExtrapolationEngine", "TwelveMonthsSummationEngine"):
    #             if key in item:
    #                 val = item[key]
    #                 bucket = int(percentile_size * (val // percentile_size))
    #                 observations[key][bucket] += 1
    #     return observations
