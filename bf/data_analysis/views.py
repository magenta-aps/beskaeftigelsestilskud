# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import dataclasses
import json
from collections import defaultdict
from decimal import Decimal

from data_analysis.models import CalculationResult
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model
from django.http import HttpResponse
from django.views import View
from django.views.generic import DetailView
from django.views.generic.list import (
    MultipleObjectMixin,
    MultipleObjectTemplateResponseMixin,
)
from project.util import group

from bf.calculate import (
    CalculationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import ASalaryReport, Person
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


class EmploymentListView(
    LoginRequiredMixin, MultipleObjectMixin, MultipleObjectTemplateResponseMixin, View
):

    template_name = "data_analysis/employment_list.html"

    def get(self, request, *args, **kwargs):
        self.year = self.kwargs["year"]
        self.object_list = self.get_objects()
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year"] = self.year
        return context

    def get_objects(self):
        reports = ASalaryReport.objects.filter(
            person_month__person_year__year=self.year
        ).select_related(
            "person_month",
            "person_month__person_year",
            "person_month__person_year__person",
        )
        by_person_employer = defaultdict(list)
        rows = []
        for report in reports:
            # by_person_employer[report.person.pk][report.employer.pk].append(report)
            by_person_employer[f"{report.person.pk}_{report.employer.pk}"].append(
                report
            )

        for reportlist in by_person_employer.values():
            first = reportlist[0]
            calculations = group(
                CalculationResult.objects.filter(a_salary_report__in=reportlist),
                "engine",
            )
            offsets = {}
            for engine, engine_calculations in calculations.items():
                # Percent offset.
                # Basically, how much off is the sum of estimations from the sum of actual values
                offsets[engine] = (
                    100
                    * sum(
                        [
                            (
                                (ec.absdiff / ec.actual_year_result)
                                if ec.actual_year_result
                                else 0
                            )
                            for ec in engine_calculations
                        ]
                    )
                    / len(engine_calculations)
                )
            row = {
                "person": first.person,
                "employer": first.employer,
                "actual_sum": sum([x.amount for x in reportlist]),
            }
            row.update(offsets)
            rows.append(row)
        return rows
