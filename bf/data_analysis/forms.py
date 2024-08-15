# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from bf.models import PersonYear, Year


class PersonYearListOptionsForm(forms.Form):
    has_a = forms.ChoiceField(
        label="A-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har A-indkomst"),
            (False, "Har ikke A-indkomst"),
        ),
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )

    has_b = forms.ChoiceField(
        label="B-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har B-indkomst"),
            (False, "Har ikke B-indkomst"),
        ),
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )

    order_by = forms.ChoiceField(
        choices=(
            (f"{prefix}{field}", f"{prefix}{field}")
            for field in (
                "person__cpr",
                "InYearExtrapolationEngine",
                "TwelveMonthsSummationEngine",
                "SameAsLastMonthEngine",
                "actual_sum",
                "payout",
                "correct_payout",
                "payout_offset",
            )
            for prefix in ("", "-")
        ),
        required=False,
    )

    min_offset = forms.IntegerField(
        label="Min. offset [%]",
        widget=forms.widgets.NumberInput(attrs={"class": "form-control"}),
        required=False,
    )
    max_offset = forms.IntegerField(
        label="Max. offset [%]",
        widget=forms.widgets.NumberInput(attrs={"class": "form-control"}),
        required=False,
    )
    selected_model = forms.ChoiceField(
        label="Model",
        choices=(
            (None, "Alle"),
            ("InYearExtrapolationEngine", "InYearExtrapolationEngine"),
            ("TwelveMonthsSummationEngine", "TwelveMonthsSummationEngine"),
        ),
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )


class HistogramOptionsForm(PersonYearListOptionsForm):
    year = forms.ChoiceField(
        choices=[],  # populated in `__init__`
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
        label=_("År"),
    )

    resolution = forms.ChoiceField(
        choices=[
            (1, "1%"),
            (10, "10%"),
        ],
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
        label=_("Opløsning"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = [
            (self.get_year_url(year), year.year)
            for year in Year.objects.order_by("year")
        ]

    def get_year_url(self, year):
        return reverse("data_analysis:histogram", kwargs={"year": year.year})


class PersonAnalysisOptionsForm(forms.Form):
    year = forms.ChoiceField(
        choices=[],  # populated in `__init__`
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
        label=_("År"),
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop("instance", None)
        year = kwargs.pop("year", None)
        super().__init__(*args, **kwargs)
        person_years = PersonYear.objects.select_related("year").filter(person=instance)
        current_person_year = person_years.filter(year__year=year)
        self.fields["year"].choices = [
            (
                self._get_year_url(person_year),
                person_year.year.year,
            )
            for person_year in person_years
        ]
        if current_person_year.exists():
            self.fields["year"].initial = self._get_year_url(
                current_person_year.first()
            )

    def _get_year_url(self, person_year):
        return reverse(
            "data_analysis:person_analysis",
            kwargs={"pk": person_year.person.pk, "year": person_year.year.year},
        )
