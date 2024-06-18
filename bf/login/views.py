# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    REDIRECT_FIELD_NAME,
    authenticate,
    login,
    logout,
)
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView
from login.forms import AuthenticationForm


class LoginView(DjangoLoginView):
    template_name = "login/login.html"
    form_class = AuthenticationForm

    def get_success_url(self):
        return self.back or reverse("bf:root")

    def get(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            user = authenticate(
                request=self.request, saml_data=self.request.session.get("saml")
            )
            if user and user.is_authenticated:
                login(
                    request=self.request,
                    user=user,
                    backend="django_mitid_auth.saml.backend.Saml2Backend",
                )
            if not self.request.user.is_authenticated:
                response = super().get(request, *args, **kwargs)
                if self.back:
                    response.set_cookie(
                        "back", self.back, secure=True, httponly=True, samesite="None"
                    )
                return response
        backpage = self.request.COOKIES.get("back")
        if backpage:
            return redirect(backpage)
        return redirect("bf:root")

    def get_context_data(self, **context):
        return super().get_context_data(
            **{
                **context,
                "back": self.back,
            }
        )

    @property
    def back(self):
        return self.request.GET.get("back") or self.request.GET.get(REDIRECT_FIELD_NAME)


class LogoutView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        if (
            self.request.session.get(BACKEND_SESSION_KEY)
            == "django_mitid_auth.saml.backend.Saml2Backend"
            or "saml" in self.request.session
        ):
            return reverse("login:mitid:logout")
        else:
            logout(self.request)
            return settings.LOGOUT_REDIRECT_URL
