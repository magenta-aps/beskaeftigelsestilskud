# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import copy
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from operator import itemgetter
from stat import S_ISREG
from typing import List
from urllib.parse import urlencode

from common.models import EngineViewPreferences
from common.utils import SuilaJSONEncoder
from common.view_mixins import ViewLogMixin
from data_analysis.forms import (
    CsvReportOptionsForm,
    HistogramOptionsForm,
    JobListOptionsForm,
    PersonAnalysisOptionsForm,
    PersonYearListOptionsForm,
)
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Func, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.forms.models import model_to_dict
from django.http import FileResponse, HttpResponse
from django.http.response import HttpResponseForbidden, HttpResponseNotFound
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, View
from django.views.generic.list import ListView
from login.view_mixins import LoginRequiredMixin
from project.util import params_no_none, strtobool

from suila.data import engine_keys
from suila.estimation import EstimationEngine
from suila.forms import CalculatorForm
from suila.models import (
    IncomeType,
    JobLog,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
    Year,
)
from suila.simulation import Simulation
from suila.view_mixins import PermissionsRequiredMixin


class SimulationJSONEncoder(SuilaJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Simulation):
            return {
                "person": obj.person,
                "year_start": obj.year_start,
                "year_end": obj.year_end,
                "rows": obj.result.rows,
                "calculation_methods": obj.calculation_methods,
            }
        return super().default(obj)


class PersonAnalysisView(
    LoginRequiredMixin, PermissionsRequiredMixin, ViewLogMixin, DetailView, FormView
):
    model = Person
    context_object_name = "person"
    template_name = "data_analysis/person_analysis.html"
    form_class = PersonAnalysisOptionsForm
    required_model_permissions = [
        "suila.view_person",
        "suila.view_personyear",
        "suila.view_data_analysis",
    ]

    @property
    def matomo_pagename(self):
        return (
            f"Estimeringsoverblik {self.year_range_string} "
            f"for person id {self.object.id}"
        )

    @property
    def year_range_string(self):
        if self.year_start == self.year_end:
            return str(self.year_start)
        return f"{self.year_start} - {self.year_end}"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.income_type = None
        # By default, only show last year.
        year1 = self.object.last_year.year.year
        year2 = self.object.last_year.year.year
        self.year_start = min(year1, year2)
        self.year_end = max(year1, year2)
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        income_type_raw = form.cleaned_data["income_type"]
        if income_type_raw:
            self.income_type = IncomeType(income_type_raw)

        year1 = int(form.cleaned_data["year_start"] or self.object.last_year.year.year)
        year2 = int(form.cleaned_data["year_end"] or self.object.last_year.year.year)
        self.year_start = min(year1, year2)
        self.year_end = max(year1, year2)
        return self.render_to_response(
            self.get_context_data(object=self.object, form=form)
        )

    def get_context_data(self, form=None, **kwargs):
        if form is not None and form.is_valid():
            simulation = Simulation(
                EstimationEngine.instances(),
                self.get_object(),
                year_start=self.year_start,
                year_end=self.year_end,
                income_type=self.income_type,
                calculation_methods={
                    year: Year.objects.get(year=year).calculation_method
                    for year in range(self.year_start, self.year_end + 1)
                },
            )
            chart_data = json.dumps(simulation, cls=SimulationJSONEncoder)
            person_years = self.object.personyear_set.filter(
                year__year__gte=self.year_start,
                year__year__lte=self.year_end,
            ).order_by("year__year")
        else:
            chart_data = "{}"
            person_years = self.object.personyear_set.all()

        self.log_view(person_years)
        return super().get_context_data(
            **{
                **kwargs,
                "chart_data": chart_data,
                "person_years": person_years,
                "config": {
                    "payout_trivial_limit": settings.CALCULATION_TRIVIAL_LIMIT,
                },
            }
        )

    def get_form_kwargs(self):
        data = {
            "year_start": self.year_start,
            "year_end": self.year_end,
        }
        data.update(self.request.GET.dict())
        return {
            **super().get_form_kwargs(),
            "data": data,
            "instance": self.object,
        }


class PersonYearEstimationMixin:

    def get_queryset(self):
        qs = PersonYear.objects.filter(year=self.year).select_related("person")

        form = self.get_form()
        if form.is_valid():

            has_a = form.cleaned_data["has_a"]
            if has_a not in (None, ""):
                qs = qs.annotate(
                    a_count=Subquery(
                        MonthlyIncomeReport.objects.filter(
                            person_month__person_year=OuterRef("pk"), a_income__gt=0
                        )
                        .order_by()
                        .values("id")
                        .annotate(count=Func(F("id"), function="COUNT"))
                        .values("count")
                    )
                )
                if strtobool(has_a):
                    qs = qs.filter(a_count__gt=0)
                else:
                    qs = qs.filter(a_count=0)

            has_b = form.cleaned_data["has_b"]
            if has_b not in (None, ""):
                if strtobool(has_b):
                    qs = qs.filter(Q(b_income__gt=0) | Q(b_expenses__gt=0))
                else:
                    qs = qs.filter(b_income=0, b_expenses=0)

        for engine_class in EstimationEngine.classes():
            engine_name = engine_class.__name__
            for income_type in engine_class.valid_income_types:
                qs = qs.annotate(
                    **{
                        f"{engine_name}_mean_error_{income_type}": Subquery(
                            PersonYearEstimateSummary.objects.filter(
                                person_year=OuterRef("pk"),
                                estimation_engine=engine_name,
                                income_type=income_type,
                            ).values("mean_error_percent")
                        ),
                        f"{engine_name}_rmse_{income_type}": Subquery(
                            PersonYearEstimateSummary.objects.filter(
                                person_year=OuterRef("pk"),
                                estimation_engine=engine_name,
                                income_type=income_type,
                            ).values("rmse_percent")
                        ),
                    }
                )

        qs = qs.annotate(
            month_income_sum=Coalesce(Sum("personmonth__amount_sum"), Decimal("0.00"))
        )
        qs = qs.annotate(
            actual_sum=F("month_income_sum")
            + F("b_income")
            - F("b_expenses")
            - F("catchsale_expenses")
        )

        qs = qs.annotate(payout=Sum("personmonth__benefit_transferred"))

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

        return qs

    @property
    def year(self):
        return self.kwargs["year"]


class PersonListView(
    PersonYearEstimationMixin,
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    ViewLogMixin,
    ListView,
    FormView,
):
    paginate_by = 30
    model = PersonYear
    template_name = "data_analysis/personyear_list.html"
    form_class = PersonYearListOptionsForm
    default_ordering = "person__cpr"
    required_model_permissions = [
        "suila.view_person",
        "suila.view_personyear",
        "suila.view_data_analysis",
    ]

    @property
    def matomo_pagename(self):
        return f"Estimeringsoverblik {self.year}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object_list = None

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "data": self.request.GET,
        }

    def get_ordering(self) -> List[str]:
        ordering = self.request.GET.get("order_by") or self.default_ordering
        return ordering.split(",")

    def get_queryset(self):
        qs = super().get_queryset()
        form = self.get_form()

        if form.is_valid():
            cpr = form.cleaned_data.get("cpr", None)
            if cpr:
                qs = qs.filter(person__cpr__icontains=cpr)
            has_zero_income = form.cleaned_data["has_zero_income"]
            if not has_zero_income:
                qs = qs.filter(actual_sum__gt=Decimal(0))
        else:
            qs = qs.none()

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
        context["engines"] = EstimationEngine.classes()

        preferences, _ = EngineViewPreferences.objects.get_or_create(
            user=self.request.user
        )
        columns = []
        for key in engine_keys:
            columns.append([key, key, getattr(preferences, "show_" + key)])
        context["columns"] = columns

        self.log_view(context["object_list"])

        return context


class HistogramView(
    LoginRequiredMixin,
    PermissionsRequiredMixin,
    PersonYearEstimationMixin,
    ViewLogMixin,
    FormView,
):
    template_name = "data_analysis/histogram.html"
    form_class = HistogramOptionsForm
    required_model_permissions = [
        "suila.view_person",
        "suila.view_personyear",
        "suila.view_data_analysis",
    ]

    @property
    def matomo_pagename(self):
        return f"Histogram {self.year}"

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") == "json":
            return HttpResponse(
                json.dumps(self.get_histogram(), cls=DjangoJSONEncoder),
                content_type="application/json",
            )
        self.log_view()
        return super().get(request, *args, **kwargs)  # pragma: no cover

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Make `data` a mutable dict, as we need to update it below
        kwargs["data"] = copy.copy(self.request.GET)
        # Set resolution to 10% if not provided by GET parameters
        kwargs["data"].setdefault("resolution", "10")
        # Set metric to ME if not provided by GET parameters
        kwargs["data"].setdefault("metric", "mean_error")
        kwargs["data"].setdefault("income_type", "A")
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
        person_years = self.get_queryset().filter(actual_sum__gt=0)
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


class UpdateEngineViewPreferences(View):
    model = EngineViewPreferences

    def post(self, request, *args, **kwargs):
        preferences, _ = self.model.objects.get_or_create(user=self.request.user)
        for field in self.model._meta.fields:
            if field.name in request.POST and field.name.startswith("show_"):
                show_field = request.POST[field.name].lower() == "true"
                setattr(preferences, field.name, show_field)
        preferences.save()
        return HttpResponse("ok")


class JobListView(
    LoginRequiredMixin, PermissionsRequiredMixin, ViewLogMixin, ListView, FormView
):
    paginate_by = 30
    model = JobLog
    template_name = "data_analysis/job_list.html"
    form_class = JobListOptionsForm
    default_ordering = "-runtime"
    required_model_permissions = ["suila.view_joblog"]
    matomo_pagename = "Jobliste"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.object_list = None

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "data": self.request.GET,
        }

    def get_ordering(self) -> List[str]:
        ordering = self.request.GET.get("order_by") or self.default_ordering
        return ordering.split(",")

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.order_by(*self.get_ordering())
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

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

        self.log_view(self.object_list)
        return context


class CsvFileReportListView(
    LoginRequiredMixin, PermissionsRequiredMixin, ViewLogMixin, ListView, FormView
):
    form_class = CsvReportOptionsForm
    template_name = "data_analysis/report_list.html"
    matomo_pagename = "CsvRapportListe"
    default_ordering = "filename"
    required_model_permissions = ["suila.can_download_reports"]

    def get_ordering(self) -> str:
        return self.request.GET.get("order_by") or self.default_ordering

    def get_queryset(self):
        folder: str = settings.LOCAL_PRISME_CSV_STORAGE_FULL  # type: ignore[misc]
        items = []
        for filename in os.listdir(folder):
            fullpath = os.path.join(folder, filename)
            stat: os.stat_result = os.stat(fullpath)
            if S_ISREG(stat.st_mode):  # Regular file
                items.append(
                    {
                        "filename": filename,
                        "url": reverse(
                            "data_analysis:csv_report_download",
                            kwargs={"filename": filename},
                        ),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.get_current_timezone()
                        ),
                    }
                )
        ordering = self.get_ordering()
        reverse_order = False
        if ordering[0] == "-":
            ordering = ordering[1:]
            reverse_order = True
        items = sorted(items, key=itemgetter(ordering), reverse=reverse_order)
        return items

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "data": self.request.GET,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        form.full_clean()
        params = params_no_none(form.cleaned_data)
        current_order_by = params.pop("order_by", None) or self.default_ordering
        sort_params = {}
        for value, label in form.fields["order_by"].choices:
            order_by = value if value != current_order_by else ("-" + value)
            sort_params[value] = urlencode({**params, "order_by": order_by})
        context["sort_params"] = sort_params
        context["order_current"] = current_order_by
        self.log_view()
        return context


class CsvFileReportDownloadView(LoginRequiredMixin, PermissionsRequiredMixin, View):

    required_model_permissions = ["suila.can_download_reports"]

    def get(self, request, *args, **kwargs):
        filename = kwargs["filename"]
        fullpath = os.path.join(
            settings.LOCAL_PRISME_CSV_STORAGE_FULL, filename  # type: ignore[misc]
        )
        if "/" in filename:  # do not trust the user input
            return HttpResponseForbidden()
        if os.path.isfile(fullpath):
            return FileResponse(
                open(fullpath, "rb"), as_attachment=True, filename=filename
            )
        return HttpResponseNotFound()


class CalculationParametersListView(
    LoginRequiredMixin, PermissionsRequiredMixin, ListView, FormView
):
    model = Year
    template_name = "data_analysis/calculation_parameters_list.html"
    form_class = CalculatorForm

    @property
    def next_year(self):
        return date.today().year + 1

    @property
    def this_year(self):
        return date.today().year

    def get_queryset(self):
        return super().get_queryset().filter(year__lte=self.this_year)

    def get_initial(self):
        year, _ = Year.objects.get_or_create(year=self.next_year)
        method = year.calculation_method
        if method is not None:
            return model_to_dict(method)

    def get_context_data(self, **kwargs):
        methods = set(
            filter(None, [year.calculation_method for year in self.object_list])
        )
        return super().get_context_data(
            **{
                **kwargs,
                "graph_points": json.dumps(
                    {method.pk: method.graph_points for method in methods},
                    cls=SuilaJSONEncoder,
                ),
                "next_year": self.next_year,
            }
        )
