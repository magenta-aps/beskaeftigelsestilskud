from django.urls import path
from mitid_test import views

app_name = "mitid_test"

urlpatterns = [
    path("clear_session/", views.ClearSessionView.as_view()),
    path("privilege0/", views.Privilege0View.as_view()),
    path("privilege1/", views.Privilege1View.as_view()),
    path("privilege3/", views.Privilege3View.as_view()),
    path("force_auth/", views.ForceAuthView.as_view()),
    path("show_session/", views.ShowSession.as_view()),
    path("list_sessions/", views.ListSessions.as_view()),
]
