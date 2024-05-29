from typing import List

from django.urls import URLPattern, URLResolver, path

from bf.views import RootView

app_name = "bf"


urlpatterns: List[URLResolver | URLPattern] = [
    path("", RootView.as_view(), name="root"),
]
