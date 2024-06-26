# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import dataclasses
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Dict, List

from data_analysis.models import CalculationResult
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet
from django.http import HttpResponse
from django.views import View
from django.views.generic import DetailView
from django.views.generic.list import (
    ListView,
    MultipleObjectMixin,
    MultipleObjectTemplateResponseMixin,
)
from project.util import group

from bf.calculate import (
    CalculationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import MonthlyAIncomeReport, Person, PersonYear
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


class PersonListView(
    LoginRequiredMixin, MultipleObjectMixin, MultipleObjectTemplateResponseMixin, View
):

    template_name = "data_analysis/personyear_list.html"

    @property
    def year(self):
        return self.kwargs["year"]

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_objects()
        if request.GET.get("format") == "json":
            return HttpResponse(
                json.dumps(self.get_histogram(), cls=DjangoJSONEncoder),
                content_type="application/json",
            )
        return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year
        return context

    def get_objects(self):
        person_years: QuerySet[PersonYear] = PersonYear.objects.filter(
            year=self.year
        ).select_related("person")
        items = []

        calculation_results: Dict[int, List[CalculationResult]] = group(
            CalculationResult.annotate_person_year(
                CalculationResult.objects.all()
            ).filter(f_person_year__in=person_years),
            "f_person_year",
        )
        for person_year in person_years:
            person_calculation_results = group(
                calculation_results[person_year.pk], "engine"
            )
            actual_sum = person_year.sum_amount
            item = {"person": person_year.person, "actual_sum": actual_sum}
            if person_calculation_results:
                for engine, engine_calculations in person_calculation_results.items():
                    engine_offset_pct = (
                        100
                        * sum([ec.absdiff for ec in engine_calculations]) / actual_sum
                        / len(engine_calculations)
                    )
                    item[engine] = engine_offset_pct
            else:
                item["InYearExtrapolationEngine"] = Decimal(0)
                item["TwelveMonthsSummationEngine"] = Decimal(0)
            items.append(item)
        return items

    def get_histogram(self) -> defaultdict:
        percentile_size = 10
        observations: defaultdict = defaultdict(Counter)
        for item in self.object_list:
            for key in ("InYearExtrapolationEngine", "TwelveMonthsSummationEngine"):
                if key in item:
                    val = item[key]
                    bucket = int(percentile_size * (val // percentile_size))
                    observations[key][bucket] += 1
        return observations
