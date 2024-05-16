from typing import List

from django.urls import URLPattern, URLResolver, path
from django.views.generic import TemplateView

app_name = "bf"

urlpatterns: List[URLResolver | URLPattern] = [
    path("", TemplateView.as_view(template_name="bf/base.html"))
]


