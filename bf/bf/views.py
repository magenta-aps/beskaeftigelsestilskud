# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Callable

from django.db.models import Count, Field
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, TemplateView
from django_filters import CharFilter, ChoiceFilter, FilterSet
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


class CategoryChoiceFilter(ChoiceFilter):
    _isnull = "isnull"

    def __init__(self, *args, **kwargs):
        field = kwargs.pop("field")
        super().__init__(*args, choices=self._get_choices(field.field), **kwargs)

    def filter(self, qs, value):
        if value == self._isnull:
            return self.get_method(qs)(**{"%s__isnull" % self.field_name: True})
        return super().filter(qs, value)  # pragma: no cover

    def _get_choices(self, field: Field) -> Callable:
        def _func():
            return [
                (
                    val[field.name] or self._isnull,
                    f"{val[field.name] or _('Ingen')} ({val['count']})",
                )
                for val in field.model.objects.values(field.name)
                .annotate(count=Count("id"))
                .order_by(field.name)
            ]

        return _func


class PersonFilterSet(FilterSet):
    cpr = CharFilter("cpr", label=_("CPR-nummer"))
    name = CharFilter("name", lookup_expr="icontains", label=_("Navn"))
    full_address = CharFilter(
        "full_address", lookup_expr="icontains", label=_("Adresse")
    )
    civil_state = CategoryChoiceFilter(field=Person.civil_state, label=_("Civilstand"))
    location_code = CategoryChoiceFilter(
        field=Person.location_code, label=_("Stedkode")
    )


class PersonSearchView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Person
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "bf/person_search.html"


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "bf/person_detail.html"
