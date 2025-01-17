# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.forms import ModelForm, Textarea
from django.forms.models import inlineformset_factory

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
