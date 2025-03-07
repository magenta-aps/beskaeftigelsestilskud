# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from common.fields import CPRField
from common.form_mixins import BootstrapForm
from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from dynamic_forms import DynamicField, DynamicFormMixin

from suila.data import engine_keys
from suila.models import IncomeType, Year


class PersonYearListOptionsForm(BootstrapForm):
    has_a = forms.ChoiceField(
        label="A-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har A-indkomst"),
            (False, "Har ikke A-indkomst"),
        ),
        required=False,
    )

    has_b = forms.ChoiceField(
        label="B-indkomst",
        choices=(
            (None, "Alle"),
            (True, "Har B-indkomst"),
            (False, "Har ikke B-indkomst"),
        ),
        required=False,
    )

    has_zero_income = forms.BooleanField(
        label="Har indkomst",
        required=False,
        widget=forms.widgets.Select(
            choices=(
                (False, "Kun dem der har indkomst"),
                (True, "Alle"),
            ),
        ),
    )

    order_by = forms.ChoiceField(
        choices=(
            (f"{prefix}{field}", f"{prefix}{field}")
            for field in (
                ("person__cpr",)
                + tuple([ek + "_mean_error_A" for ek in engine_keys])
                + tuple([ek + "_rmse_A" for ek in engine_keys])
                + tuple([ek + "_mean_error_B" for ek in engine_keys])
                + tuple([ek + "_rmse_B" for ek in engine_keys])
                + (
                    "month_income_sum",
                    "catchsale_expenses",
                    "b_income",
                    "b_expenses",
                    "actual_sum",
                    "payout",
                    "correct_payout",
                    "payout_offset",
                    "stability_score_a",
                    "stability_score_b",
                    "preferred_estimation_engine_a",
                    "preferred_estimation_engine_b",
                )
            )
            for prefix in ("", "-")
        ),
        required=False,
    )

    min_offset = forms.IntegerField(
        label="Min. offset [%]",
        widget=forms.widgets.NumberInput(),
        required=False,
    )
    max_offset = forms.IntegerField(
        label="Max. offset [%]",
        widget=forms.widgets.NumberInput(),
        required=False,
    )
    selected_model = forms.ChoiceField(
        label="Model / metric",
        choices=[
            (None, "Alle"),
        ]
        + [
            (f"{engine}_mean_error_{income_type}", f"{engine} (ME) ({income_type})")
            for engine in engine_keys
            for income_type in IncomeType
        ]
        + [
            (f"{engine}_rmse_{income_type}", f"{engine} (RMSE) ({income_type})")
            for engine in engine_keys
            for income_type in IncomeType
        ]
        + [("payout_offset", "Tilskudsafvigelse")],
        required=False,
    )
    cpr = CPRField(
        required=False,
        label="Cpr-nummer",
    )


class HistogramOptionsForm(PersonYearListOptionsForm):
    year = forms.ChoiceField(
        choices=[],  # populated in `__init__`
        required=False,
        label=_("År"),
    )

    resolution = forms.ChoiceField(
        choices=[
            (1, "1%"),
            (10, "10%"),
            (100, "100kr"),
            (200, "200kr"),
            (1000, "1000kr"),
        ],
        required=False,
        label=_("Opløsning"),
    )
    metric = forms.ChoiceField(
        choices=[
            ("mean_error", "Gennemsnitlig afvigelse"),
            ("rmse", "Kvadratroden af den gennemsnitlige kvadratafvigelse"),
            ("payout_offset", "Tilskudsafvigelse"),
        ],
        required=False,
        label=_("Metrik"),
    )
    income_type = forms.ChoiceField(
        choices=IncomeType,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = [
            (self.get_year_url(year), year.year)
            for year in Year.objects.order_by("year")
        ]

    def get_year_url(self, year):
        return reverse("data_analysis:histogram", kwargs={"year": year.year})


class PersonAnalysisOptionsForm(DynamicFormMixin, BootstrapForm):
    year_start = DynamicField(
        forms.ChoiceField,
        choices=lambda form: [(year, year) for year in form.years],
        required=False,
        label=_("År"),
    )
    year_end = DynamicField(
        forms.ChoiceField,
        choices=lambda form: [(year, year) for year in form.years],
        required=False,
        label=_("År"),
    )

    income_type = forms.ChoiceField(
        choices=[(None, _("Alle"))]
        + [(choice.value, choice.label) for choice in IncomeType],
        label=_("Indkomsttype"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop("instance", None)
        person_years = instance.personyear_set.all().select_related("year")
        self.years = sorted([person_year.year.year for person_year in person_years])
        super().__init__(*args, **kwargs)


class JobListOptionsForm(BootstrapForm):
    order_by = forms.ChoiceField(
        choices=(
            (f"{prefix}{field}", f"{prefix}{field}")
            for field in (
                "name",
                "runtime",
                "status",
                "year_param",
                "month_param",
                "cpr_param",
                "type_param",
                "count_param",
            )
            for prefix in ("", "-")
        ),
        required=False,
    )
