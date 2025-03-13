# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import List

from django.urls import URLPattern, URLResolver, path
from django.views.generic import TemplateView

from suila.api import api
from suila.views import (
    CalculatorView,
    EboksMessageView,
    GraphView,
    PersonDetailEboksView,
    PersonDetailIncomeView,
    PersonDetailNotesAttachmentView,
    PersonDetailNotesView,
    PersonDetailView,
    PersonGraphView,
    PersonSearchView,
    RootView,
)

app_name = "suila"


urlpatterns: List[URLResolver | URLPattern] = [
    path("api/", api.urls, name="api"),
    path("", RootView.as_view(), name="root"),
    path("calculator/", CalculatorView.as_view(), name="calculator"),
    path("graph/", GraphView.as_view(), name="graph"),
    path("faq/", TemplateView.as_view(template_name="suila/faq.html"), name="faq"),
    path(
        "about/",
        TemplateView.as_view(template_name="suila/about.html"),
        name="about",
    ),
    path("persons/", PersonSearchView.as_view(), name="person_search"),
    path("persons/<int:pk>/", PersonDetailView.as_view(), name="person_detail"),
    path("persons/<int:pk>/graph/", PersonGraphView.as_view(), name="person_graph"),
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
    path(
        "persons/<int:pk>/eboks/",
        PersonDetailEboksView.as_view(),
        name="person_detail_eboks",
    ),
    path(
        "person/<int:pk>/msg/<int:year>/<int:month>/<str:type>/",
        EboksMessageView.as_view(),
        name="person_message",
    ),
]
