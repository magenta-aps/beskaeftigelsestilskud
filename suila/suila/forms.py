# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from urllib.parse import quote_plus, unquote_plus

from common.form_mixins import BootstrapForm
from django.forms import (
    CharField,
    ChoiceField,
    DecimalField,
    FileInput,
    Form,
    HiddenInput,
    IntegerField,
    ModelForm,
    Select,
    Textarea,
)
from django.forms.fields import BooleanField
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from suila.models import (
    Note,
    NoteAttachment,
    Person,
    PersonYear,
    WorkingTaxCreditCalculationMethod,
)


class NoteForm(ModelForm):
    class Meta:
        model = Note
        fields = ("text",)
        widgets = {"text": Textarea(attrs={"rows": 4, "class": "form-control"})}


class NoteAttachmentForm(ModelForm):
    class Meta:
        widgets = {"file": FileInput(attrs={"class": "form-control"})}

    def save(self, commit=True):
        instance = super().save(False)
        instance.content_type = self.cleaned_data["file"].content_type
        instance.save(commit)
        return instance


NoteAttachmentFormSet = inlineformset_factory(
    parent_model=Note,
    model=NoteAttachment,
    form=NoteAttachmentForm,
    fields=("file",),
    extra=1,
)


class CalculationParametersForm(BootstrapForm):

    benefit_rate_percent = DecimalField(
        max_digits=5,
        min_value=Decimal(0),
        decimal_places=3,
        required=True,
        localize=True,
        label=_("Beskæftigelsesfradrag stigningssats frem til loft"),
    )
    personal_allowance = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=True,
        localize=True,
        label=_("Personfradrag"),
    )
    standard_allowance = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=True,
        localize=True,
        label=_("Standardfradrag"),
    )
    max_benefit = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=True,
        localize=True,
        label=_("Maksimalt Suila-tapit/år"),
    )
    scaledown_rate_percent = DecimalField(
        max_digits=5,
        min_value=Decimal(0),
        decimal_places=3,
        required=True,
        localize=True,
        label=_("Aftrapningsprocent efter aftrapningsstart"),
    )
    scaledown_ceiling = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=True,
        localize=True,
        label=_("Beløb - aftrapningsstart"),
    )


class CalculatorForm(BootstrapForm):
    estimated_month_income = DecimalField(
        required=False,
        label=_("Estimeret månedsindkomst"),
    )
    estimated_year_income = DecimalField(
        required=True, label=_("Estimeret årsindkomst")
    )

    method = ChoiceField(
        choices=[
            (cls.__name__, cls.__name__)
            for cls in WorkingTaxCreditCalculationMethod.__subclasses__()
        ],
        widget=HiddenInput,
        required=False,
    )

    benefit_rate_percent = DecimalField(
        max_digits=5,
        min_value=Decimal(0),
        decimal_places=3,
        required=False,
        localize=True,
    )
    personal_allowance = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=False,
        localize=True,
    )
    standard_allowance = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=False,
        localize=True,
    )
    max_benefit = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=False,
        localize=True,
    )
    scaledown_rate_percent = DecimalField(
        max_digits=5,
        min_value=Decimal(0),
        decimal_places=3,
        required=False,
        localize=True,
    )
    scaledown_ceiling = DecimalField(
        max_digits=12,
        min_value=Decimal(0),
        decimal_places=2,
        required=False,
        localize=True,
    )


class IncomeSignalFilterForm(Form):
    filter_key = ChoiceField(
        label=_("Kilde"),
        error_messages={
            "invalid_choice": _(
                "Marker en gyldig valgmulighed. %(value)s er ikke en af de "
                "tilgængelige valgmuligheder",
            ),
        },
        required=False,
        widget=Select(attrs={"data-submit-onchange": "true"}),
    )

    def __init__(self, *args, **kwargs):
        signals = kwargs.pop("signals", [])
        super().__init__(*args, **kwargs)
        self.fields["filter_key"].choices = [("", _("Alle"))] + [
            (quote_plus(str(filter_key)), filter_key)
            for filter_key in sorted(set(signal.filter_key for signal in signals))
        ]
        self.fields["filter_key"].initial = unquote_plus(
            str(kwargs.get("data", {}).get("filter_key", "")),
        )

    def clean_filter_key(self) -> str:
        return unquote_plus(self.cleaned_data["filter_key"])


class ConfirmationForm(Form):
    confirmed = BooleanField(required=False)


class PersonAnnualIncomeEstimateForm(ModelForm):
    year = IntegerField(required=True)
    month = IntegerField(required=True)
    note = CharField(required=True)

    class Meta:
        model = Person
        fields = ["annual_income_estimate"]


class PauseForm(ModelForm):
    year = IntegerField(required=True)
    month = IntegerField(required=True)
    note = CharField(required=False)

    class Meta:
        model = Person
        fields = ["paused", "allow_pause", "pause_reason"]


class PersonYearEstimationEngineForm(ModelForm):
    note = CharField(required=True)
    preferred_estimation_engine_a_default = CharField(required=True)
    preferred_estimation_engine_u_default = CharField(required=True)

    class Meta:
        model = PersonYear
        fields = ["preferred_estimation_engine_a", "preferred_estimation_engine_u"]
