from data_analysis.views import PersonAnalysisView
from django.urls import URLPattern, URLResolver, path

app_name = "data_analysis"


urlpatterns: list[URLResolver | URLPattern] = [
    path("person/<int:pk>/", PersonAnalysisView.as_view(), name="person_analysis"),
]
