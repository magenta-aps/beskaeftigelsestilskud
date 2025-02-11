# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.forms import DecimalField, Form, ModelForm, Textarea
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from suila.models import Note, NoteAttachment


class NoteForm(ModelForm):
    class Meta:
        model = Note
        fields = ("text",)
        widgets = {"text": Textarea(attrs={"rows": 4, "class": "form-control"})}


class NoteAttachmentForm(ModelForm):

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


class CalculateBenefitForm(Form):
    estimated_month_income = DecimalField(
        required=False,
        label=_("Estimeret månedsindkomst"),
    )
    estimated_year_income = DecimalField(
        required=True,
        label=_("Estimeret årsindkomst"),
    )
