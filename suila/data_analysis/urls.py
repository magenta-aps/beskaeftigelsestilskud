# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from data_analysis.views import (
    CsvFileReportDownloadView,
    CsvFileReportListView,
    HistogramView,
    JobListView,
    PersonAnalysisView,
    PersonListView,
    PersonYearEstimationEngineAUpdateView,
    PersonYearEstimationEngineUUpdateView,
    UpdateEngineViewPreferences,
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
    path(
        "user/preferences/update",
        UpdateEngineViewPreferences.as_view(),
        name="update_preferences",
    ),
    path("job_log", JobListView.as_view(), name="job_log"),
    path("csv_report", CsvFileReportListView.as_view(), name="csv_report"),
    path(
        "csv_report/<str:filename>",
        CsvFileReportDownloadView.as_view(),
        name="csv_report_download",
    ),
    path(
        "person_year/<int:pk>/set_estimation_engine_a/",
        PersonYearEstimationEngineAUpdateView.as_view(),
        name="set_personyear_estimation_engine_a",
    ),
    path(
        "person_year/<int:pk>/set_estimation_engine_u/",
        PersonYearEstimationEngineUUpdateView.as_view(),
        name="set_personyear_estimation_engine_u",
    ),
]
