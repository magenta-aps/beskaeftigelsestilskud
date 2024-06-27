# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from data_analysis.views import HistogramView, PersonAnalysisView, PersonListView
from django.urls import URLPattern, URLResolver, path

app_name = "data_analysis"


urlpatterns: list[URLResolver | URLPattern] = [
    path(
        "person/<int:pk>/<int:year>/",
        PersonAnalysisView.as_view(),
        name="person_analysis",
    ),
    path("person/<int:year>/", PersonListView.as_view(), name="person_years"),
    path("person/<int:year>/histogram/", HistogramView.as_view(), name="histogram"),
]
