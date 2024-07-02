from urllib.parse import urlencode

from django.template.defaultfilters import register


@register.filter
def urlparams(value: dict):
    return urlencode(value)
