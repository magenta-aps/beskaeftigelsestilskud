# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse

from bf.models import PersonYear


class PersonYearListOptionsForm(forms.Form):
    has_a = forms.ChoiceField(
        label="A-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har A-indkomst"),
            (False, "Har ikke A-indkomst")
        ),
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )
    has_b = forms.ChoiceField(
        label="B-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har B-indkomst"),
            (False, "Har ikke B-indkomst")
        ),
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )


class HistogramOptionsForm(PersonYearListOptionsForm):
    resolution = forms.ChoiceField(
        choices=[
            (1, "1%"),
            (10, "10%"),
        ],
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
    )

    def clean_resolution(self):
        try:
            return int(self.cleaned_data["resolution"])
        except ValueError:
            raise ValidationError("")


class PersonAnalysisOptionsForm(forms.Form):
    year = forms.ChoiceField(
        choices=[],  # populated in `__init__`
        required=False,
        widget=forms.widgets.Select(attrs={"class": "form-control"}),
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
