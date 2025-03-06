# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from urllib.parse import quote_plus, unquote_plus

from django.forms import (
    ChoiceField,
    DecimalField,
    FileInput,
    Form,
    HiddenInput,
    ModelForm,
    Textarea,
)
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from suila.models import Note, NoteAttachment, WorkingTaxCreditCalculationMethod


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


class CalculatorForm(Form):
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
    source = ChoiceField(label=_("Kilde"), required=False)

    def __init__(self, *args, **kwargs):
        signals = kwargs.pop("signals", [])
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = [("", _("Alle"))] + [
            (quote_plus(source), source)
            for source in sorted(set(signal.source for signal in signals))
        ]
        self.fields["source"].initial = unquote_plus(
            kwargs.get("data", {}).get("source", "")
        )

    def clean_source(self) -> str:
        return unquote_plus(self.cleaned_data["source"])
