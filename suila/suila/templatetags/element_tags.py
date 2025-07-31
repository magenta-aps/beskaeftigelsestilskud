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


@register.inclusion_tag("suila/templatetags/action_button.html", takes_context=True)
def action_button(context, title, modal_id, modal_body):
    return {  # pragma: no cover
        "title": title,
        "modal_id": modal_id,
        "modal_body": modal_body,
        **context.flatten(),
    }


@register.inclusion_tag("suila/templatetags/file_formset.html", takes_context=True)
def file_formset(context, formset, formset_name):
    return {  # pragma: no cover
        "formset": formset,
        "formset_name": formset_name,
        **context.flatten(),
    }


@register.inclusion_tag("suila/templatetags/language_picker.html", takes_context=True)
def language_picker(context):
    return {"request": context["request"]}  # pragma: no cover
