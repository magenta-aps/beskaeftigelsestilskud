# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.template.defaultfilters import register


@register.inclusion_tag("suila/templatetags/jumbo_link.html")
def jumbo_link(url, title, icon):
    return {  # pragma: no cover
        "url": url,
        "title": title,
        "icon": icon,
    }


@register.inclusion_tag("suila/templatetags/jumbo_button.html")
def jumbo_button(name, value, title, icon):
    return {  # pragma: no cover
        "name": name,
        "value": value,
        "title": title,
        "icon": icon,
    }
