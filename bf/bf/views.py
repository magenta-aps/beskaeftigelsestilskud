# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.views.generic import DetailView, TemplateView
from django_filters import FilterSet
from django_filters.views import FilterView
from django_tables2 import LinkColumn, SingleTableMixin, Table
from django_tables2.utils import Accessor
from login.view_mixins import LoginRequiredMixin

from bf.models import Person


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "bf/root.html"


class PersonTable(Table):
    class Meta:
        model = Person
        fields = ("cpr", "name", "full_address", "civil_state", "location_code")

    cpr = LinkColumn("bf:person_detail", args=[Accessor("pk")])


class PersonFilterSet(FilterSet):
    class Meta:
        model = Person
        fields = {
            "cpr": ["exact"],
            "name": ["icontains"],
            "full_address": ["icontains"],
            "civil_state": ["exact"],
            "location_code": ["exact"],
        }


class PersonSearchView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Person
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "bf/person_search.html"


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "bf/person_detail.html"
