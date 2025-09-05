# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.defaultfilters import register
from django.utils.translation import gettext


@register.filter
def translate_note(note_text: str) -> str:
    return "\n".join([gettext(p) for p in note_text.split("\n")])
