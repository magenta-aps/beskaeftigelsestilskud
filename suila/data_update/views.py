# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from data_update.forms import (
    ActionForm,
    AnnualIncomeCreateForm,
    AnnualIncomeForm,
    MonthlyIncomeCreateForm,
    MonthlyIncomeForm,
    PersonMonthCreateForm,
    PersonYearAssessmentCreateForm,
    PersonYearAssessmentForm,
    PersonYearCreateForm,
)
from django.core import management
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, UpdateView
from login.view_mixins import LoginRequiredMixin

from suila.estimation import EstimationEngine
from suila.models import (
    AnnualIncome,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
)
from suila.view_mixins import PermissionsRequiredMixin


class PersonView(LoginRequiredMixin, PermissionsRequiredMixin, DetailView):
    model = Person
    template_name = "data_update/person.html"
    required_model_permissions = [
        "suila.view_person",
    ]

    def get_object(self, queryset=None):
        return Person.objects.get(
            cpr=self.kwargs["cpr"],
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "person": self.object,
                "personyears": self.object.personyear_set.all(),
            }
        )


class PersonYearCreateView(LoginRequiredMixin, PermissionsRequiredMixin, CreateView):
    model = PersonYear
    form_class = PersonYearCreateForm
    required_model_permissions = [
        "suila.add_personyear",
    ]
    template_name = "data_update/personyear_create.html"

    def get_person(self):
        return Person.objects.get(cpr=self.kwargs["cpr"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person"] = self.get_person()
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**{**kwargs, "person": self.get_person()})

    def get_success_url(self):
        return reverse(
            "data_update:person_view",
            kwargs={"cpr": self.kwargs["cpr"]},
        )


class PersonYearView(
    LoginRequiredMixin, PermissionsRequiredMixin, DetailView, FormView
):
    model = PersonYear
    template_name = "data_update/personyear.html"
    form_class = ActionForm
    required_model_permissions = [
        "suila.view_personyear",
    ]

    def get_object(self, queryset=None):
        return PersonYear.objects.get(
            person__cpr=self.kwargs["cpr"],
            year_id=self.kwargs["year"],
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "person": self.object.person,
                "personyear": self.object,
                "months": self.object.personmonth_set.all().order_by("month"),
                "annualincomes": self.object.annual_income_statements.all(),
                "assessments": self.object.assessments.all(),
            }
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        action = form.cleaned_data["action"]
        if action == "estimate":
            EstimationEngine.estimate_all(
                self.object.year_id, self.object.person_id, count=None, dry_run=False
            )
            management.call_command(
                "autoselect_estimation_engine",
                year=self.object.year_id
                + 1,  # Will look at this year to set engine for next year
                cpr=self.object.person.cpr,
            )
        if action == "calculate":
            person_months = PersonMonth.objects.filter(
                person_year__year__year=self.object.year_id,
                person_year__person__cpr=self.object.person.cpr,
            )
            for person_month in person_months:
                management.call_command(
                    "calculate_benefit",
                    self.object.year_id,
                    person_month.month,
                    cpr=self.object.person.cpr,
                )
        return redirect(
            "data_update:personyear_view",
            cpr=self.object.person.cpr,
            year=self.object.year_id,
        )


class PersonYearSubView:
    template_name: str | None = "data_update/personyear_sub.html"

    def get_person_year(self):
        return PersonYear.objects.get(
            person__cpr=self.kwargs["cpr"],
            year_id=self.kwargs["year"],
        )

    def get_context_data(self, **kwargs):
        person_year = self.get_person_year()
        return super().get_context_data(
            **{
                **kwargs,
                "person": person_year.person,
                "personyear": person_year,
            }
        )

    def get_success_url(self):
        return reverse(
            "data_update:personyear_view",
            kwargs={"cpr": self.kwargs["cpr"], "year": self.kwargs["year"]},
        )


class PersonYearSubCreateView(PersonYearSubView):

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person_year"] = self.get_person_year()
        return kwargs


class PersonMonthCreateView(
    LoginRequiredMixin, PermissionsRequiredMixin, PersonYearSubCreateView, CreateView
):
    model = PersonMonth
    form_class = PersonMonthCreateForm
    required_model_permissions = [
        "suila.add_personmonth",
    ]


class AnnualIncomeCreateView(
    LoginRequiredMixin, PermissionsRequiredMixin, PersonYearSubCreateView, CreateView
):
    model = AnnualIncome
    form_class = AnnualIncomeCreateForm
    required_model_permissions = [
        "suila.add_annualincome",
    ]


class PersonYearAssessmentCreateView(
    LoginRequiredMixin, PermissionsRequiredMixin, PersonYearSubCreateView, CreateView
):
    model = PersonYearAssessment
    form_class = PersonYearAssessmentCreateForm
    required_model_permissions = [
        "suila.add_personyearassessment",
    ]


class PersonYearAssessmentUpdateView(
    LoginRequiredMixin, PermissionsRequiredMixin, PersonYearSubView, UpdateView
):
    required_model_permissions = [
        "suila.view_personyearassessment",
        "suila.change_personyearassessment",
    ]
    form_class = PersonYearAssessmentForm
    model = PersonYearAssessment


class PersonMonthView(LoginRequiredMixin, PermissionsRequiredMixin, DetailView):
    model = PersonMonth
    template_name = "data_update/personmonth.html"
    required_model_permissions = [
        "suila.view_personmonth",
    ]

    def get_object(self, queryset=None):
        return PersonMonth.objects.get(
            person_year__person__cpr=self.kwargs["cpr"],
            person_year__year_id=self.kwargs["year"],
            month=self.kwargs["month"],
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "person": self.object.person,
                "personyear": self.object.person_year,
                "incomereports": self.object.monthlyincomereport_set.all(),
            }
        )


class AnnualIncomeUpdateView(LoginRequiredMixin, PermissionsRequiredMixin, UpdateView):
    required_model_permissions = [
        "suila.view_annualincome",
        "suila.change_annualincome",
    ]
    form_class = AnnualIncomeForm
    model = AnnualIncome
    template_name = "data_update/annualincome.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "person": self.object.person_year.person,
                "personyear": self.object.person_year,
            }
        )

    def get_success_url(self):
        return reverse(
            "data_update:personyear_view",
            kwargs={
                "cpr": self.object.person_year.person.cpr,
                "year": self.object.person_year.year,
            },
        )


class MonthlyIncomeCreateView(LoginRequiredMixin, PermissionsRequiredMixin, CreateView):
    required_model_permissions = [
        "suila.view_monthlyincomereport",
        "suila.change_monthlyincomereport",
    ]
    form_class = MonthlyIncomeCreateForm
    model = MonthlyIncomeReport
    template_name = "data_update/monthlyincome_create.html"

    def get_person_month(self):
        return PersonMonth.objects.get(
            person_year__person__cpr=self.kwargs["cpr"],
            person_year__year_id=self.kwargs["year"],
            month=self.kwargs["month"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person_month"] = self.get_person_month()
        return kwargs

    def get_context_data(self, **kwargs):
        person_month = self.get_person_month()
        return super().get_context_data(
            **{
                **kwargs,
                "person": person_month.person_year.person,
                "personyear": person_month.person_year,
                "personmonth": person_month,
            }
        )

    def get_success_url(self):
        person_month = self.get_person_month()
        return reverse(
            "data_update:personmonth_view",
            kwargs={
                "cpr": person_month.person.cpr,
                "year": person_month.person_year.year,
                "month": person_month.month,
            },
        )


class MonthlyIncomeUpdateView(LoginRequiredMixin, PermissionsRequiredMixin, UpdateView):
    required_model_permissions = [
        "suila.view_monthlyincomereport",
        "suila.change_monthlyincomereport",
    ]
    form_class = MonthlyIncomeForm
    model = MonthlyIncomeReport
    template_name = "data_update/monthlyincome_update.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{
                **kwargs,
                "person": self.object.person_month.person,
                "personyear": self.object.person_month.person_year,
                "personmonth": self.object.person_month,
            }
        )

    def get_success_url(self):
        return reverse(
            "data_update:personmonth_view",
            kwargs={
                "cpr": self.object.person_month.person.cpr,
                "year": self.object.person_month.person_year.year,
                "month": self.object.person_month.month,
            },
        )
