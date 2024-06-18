# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import dataclasses
import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model
from django.http import HttpResponse
from django.views.generic import DetailView

from bf.calculate import (
    CalculationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import Person
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
        self.simulation = Simulation(
            [InYearExtrapolationEngine(), TwelveMonthsSummationEngine()],
            self.get_object(),
            year=2024,
        )

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") == "json":
            return HttpResponse(
                json.dumps(self.simulation, cls=SimulationJSONEncoder),
                content_type="application/json",
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context
