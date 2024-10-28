# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Callable

from django.db.models import CharField, Count, Field, Value
from django.db.models.functions import Cast, LPad
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, TemplateView
from django_filters import CharFilter, ChoiceFilter, FilterSet
from django_filters.views import FilterView
from django_tables2 import Column, SingleTableMixin, Table
from django_tables2.columns.linkcolumn import BaseLinkColumn
from django_tables2.utils import Accessor
from login.view_mixins import LoginRequiredMixin

from bf.models import Person


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "bf/root.html"


class CPRColumn(BaseLinkColumn):
    def __init__(self, *args, **kwargs):
        linkify = dict(viewname="bf:person_detail", args=[Accessor("pk")])
        kwargs.setdefault("verbose_name", _("CPR-nummer"))
        kwargs.setdefault("linkify", linkify)
        super().__init__(*args, **kwargs)


class PersonTable(Table):
    cpr = CPRColumn(accessor=Accessor("_cpr"), order_by=Accessor("_cpr"))
    name = Column(verbose_name=_("Navn"))
    full_address = Column(verbose_name=_("Adresse"))
    civil_state = Column(verbose_name=_("Civilstand"))
    location_code = Column(verbose_name=_("Stedkode"))


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
    cpr = CharFilter("_cpr", label=_("CPR-nummer"))
    name = CharFilter("name", lookup_expr="icontains", label=_("Navn"))
    full_address = CharFilter(
        "full_address", lookup_expr="icontains", label=_("Adresse")
    )
    civil_state = CategoryChoiceFilter(field=Person.civil_state, label=_("Civilstand"))
    location_code = CategoryChoiceFilter(
        field=Person.location_code, label=_("Stedkode")
    )


class PersonSearchView(LoginRequiredMixin, SingleTableMixin, FilterView):
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "bf/person_search.html"

    def get_queryset(self):
        return Person.objects.annotate(
            _cpr=LPad(Cast("cpr", CharField()), 10, Value("0"))
        ).order_by("_cpr")


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "bf/person_detail.html"
