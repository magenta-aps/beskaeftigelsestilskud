# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.core.exceptions import ValidationError


class HistogramOptionsForm(forms.Form):
    resolution = forms.ChoiceField(
        choices=[
            (1, "1%"),
            (10, "10%"),
        ],
        required=False,
    )

    def clean_resolution(self):
        try:
            return int(self.cleaned_data["resolution"])
        except ValueError:
            raise ValidationError("")
