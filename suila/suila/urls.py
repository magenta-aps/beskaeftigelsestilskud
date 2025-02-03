# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import List

from django.urls import URLPattern, URLResolver, path

from suila.api import api
from suila.views import (
    PersonDetailBenefitView,
    PersonDetailIncomeView,
    PersonDetailNotesAttachmentView,
    PersonDetailNotesView,
    PersonDetailView,
    PersonSearchView,
    RootView,
)

app_name = "suila"


urlpatterns: List[URLResolver | URLPattern] = [
    path("api/", api.urls, name="api"),
    path("", RootView.as_view(), name="root"),
    path("persons/", PersonSearchView.as_view(), name="person_search"),
    path("persons/<int:pk>/", PersonDetailView.as_view(), name="person_detail"),
    path(
        "persons/<int:pk>/benefits/",
        PersonDetailBenefitView.as_view(),
        name="person_detail_benefits",
    ),
    path(
        "persons/<int:pk>/income/",
        PersonDetailIncomeView.as_view(),
        name="person_detail_income",
    ),
    path(
        "persons/<int:pk>/notes/",
        PersonDetailNotesView.as_view(),
        name="person_detail_notes",
    ),
    path(
        "note_attachments/<int:pk>/",
        PersonDetailNotesAttachmentView.as_view(),
        name="note_attachment",
    ),
]
