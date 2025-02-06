# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.defaultfilters import register


@register.inclusion_tag("suila/templatetags/jumbo_link.html")
def jumbo_link(url, title, icon, text):
    return {  # pragma: no cover
        "url": url,
        "title": title,
        "icon": icon,
        "text": text,
    }
