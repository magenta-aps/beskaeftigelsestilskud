# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from data_update.views import (
    AnnualIncomeCreateView,
    AnnualIncomeUpdateView,
    MonthlyIncomeCreateView,
    MonthlyIncomeUpdateView,
    PersonMonthCreateView,
    PersonMonthView,
    PersonView,
    PersonYearAssessmentCreateView,
    PersonYearAssessmentUpdateView,
    PersonYearView,
)
from django.urls import URLPattern, URLResolver, path

app_name = "data_update"


urlpatterns: list[URLResolver | URLPattern] = [
    path("person/<str:cpr>", PersonView.as_view(), name="person_view"),
    path(
        "person/<str:cpr>/<int:year>",
        PersonYearView.as_view(),
        name="personyear_view",
    ),
    path(
        "person/<str:cpr>/<int:year>/<int:month>",
        PersonMonthView.as_view(),
        name="personmonth_view",
    ),
    path(
        "person/<str:cpr>/<int:year>/create_month",
        PersonMonthCreateView.as_view(),
        name="personmonth_create",
    ),
    path(
        "person/<str:cpr>/<int:year>/report/<int:pk>",
        AnnualIncomeUpdateView.as_view(),
        name="annualincome_update",
    ),
    path(
        "person/<str:cpr>/<int:year>/report/create",
        AnnualIncomeCreateView.as_view(),
        name="annualincome_create",
    ),
    path(
        "person/<str:cpr>/<int:year>/assessment/<int:pk>",
        PersonYearAssessmentUpdateView.as_view(),
        name="personyear_assessment_update",
    ),
    path(
        "person/<str:cpr>/<int:year>/assessment/create",
        PersonYearAssessmentCreateView.as_view(),
        name="personyear_assessment_create",
    ),
    path(
        "person/<str:cpr>/<int:year>/<int:month>/report/create",
        MonthlyIncomeCreateView.as_view(),
        name="monthlyincome_create",
    ),
    path(
        "person/<str:cpr>/<int:year>/<int:month>/report/<int:pk>",
        MonthlyIncomeUpdateView.as_view(),
        name="monthlyincome_update",
    ),
]
