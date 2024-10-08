# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import List

from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import TemplateView
from django_mitid_auth.saml.views import AccessDeniedView
from login.views import BeskLoginView, LogoutView, TwoFactorSetup

app_name = "login"


urlpatterns: List[URLResolver | URLPattern] = [
    path("mitid/", include("django_mitid_auth.urls", namespace="mitid")),
    path(
        "login",
        BeskLoginView.as_view(),
        name="login",
    ),
    path(
        "logout",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "error/login-timeout/",
        AccessDeniedView.as_view(template_name="login/login_timeout.html"),
        name="login-timeout",
    ),
    path(
        "error/login-repeat/",
        AccessDeniedView.as_view(template_name="login/login_repeat.html"),
        name="login-repeat",
    ),
    path(
        "error/login-nocpr/",
        AccessDeniedView.as_view(template_name="login/login_no_cpr.html"),
        name="login-no-cpr",
    ),
    path(
        "error/login-failed/",
        AccessDeniedView.as_view(template_name="login/login_failed.html"),
        name="login-failed",
    ),
    path(
        "logged_out",
        TemplateView.as_view(template_name="login/logged_out.html"),
        name="logged_out",
    ),
    path("two_factor/setup", TwoFactorSetup.as_view(), name="two_factor_setup"),
]
