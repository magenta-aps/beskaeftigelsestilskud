# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from typing import Callable

from django.db.models import CharField, Count, Field, Value
from django.db.models.functions import Cast, LPad
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, TemplateView
from django_filters import CharFilter, ChoiceFilter, FilterSet
from django_filters.views import FilterView
from django_tables2 import Column, SingleTableMixin, Table
from django_tables2.columns.linkcolumn import BaseLinkColumn
from django_tables2.utils import Accessor
from login.view_mixins import LoginRequiredMixin

from bf.models import Person
from bf.querysets import PersonKeyFigureQuerySet


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
    total_estimated_year_result = Column(
        accessor=Accessor("_total_estimated_year_result"),
        order_by=Accessor("_total_estimated_year_result"),
        verbose_name=_("Forventet samlet indtægt i indeværende år"),
    )
    total_actual_year_result = Column(
        accessor=Accessor("_total_actual_year_result"),
        order_by=Accessor("_total_actual_year_result"),
        verbose_name=_("Faktisk samlet indtægt i indeværende år"),
    )
    benefit_paid = Column(
        accessor=Accessor("_benefit_paid"),
        order_by=Accessor("_benefit_paid"),
        verbose_name=_("Beskæftigelsesfradrag til dato i indeværende år"),
    )


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
    model = Person
    table_class = PersonTable
    filterset_class = PersonFilterSet
    template_name = "bf/person_search.html"

    def get_queryset(self):
        # Get "key figure" queryset for current year and month
        today: date = timezone.now().date()
        today = date(2020, 12, 1)  # no commit
        qs = PersonKeyFigureQuerySet.from_queryset(
            super().get_queryset(),
            year=today.year,
            month=today.month,
        )
        # Add zero-padded text version of CPR to ensure proper display and sorting
        qs = qs.annotate(_cpr=LPad(Cast("cpr", CharField()), 10, Value("0")))
        # Set initial sorting (can be overridden by user)
        qs = qs.order_by("_cpr")
        return qs


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    context_object_name = "person"
    template_name = "bf/person_detail.html"
