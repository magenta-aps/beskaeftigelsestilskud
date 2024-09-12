# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from data_analysis.views import (
    HistogramView,
    PersonAnalysisView,
    PersonListView,
    UpdateEngineViewPreferences,
    ScatterPlotView
)
from django.urls import URLPattern, URLResolver, path

app_name = "data_analysis"


urlpatterns: list[URLResolver | URLPattern] = [
    path(
        "person/<int:pk>/",
        PersonAnalysisView.as_view(),
        name="person_analysis",
    ),
    path("<int:year>/person/", PersonListView.as_view(), name="person_years"),
    path("<int:year>/histogram/", HistogramView.as_view(), name="histogram"),
    path("<int:year>/scatter_plots/", ScatterPlotView.as_view(), name="scatter_plots"),
    path(
        "user/<int:pk>/preferences/update",
        UpdateEngineViewPreferences.as_view(),
        name="update_preferences",
    ),
]
