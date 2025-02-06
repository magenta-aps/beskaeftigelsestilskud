# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from common.utils import add_parameters_to_url
from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    REDIRECT_FIELD_NAME,
    authenticate,
    login,
    logout,
)
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView
from login.forms import AuthenticationForm, BeskAuthenticationTokenForm
from two_factor.views import LoginView, SetupView


class BeskLoginView(LoginView):
    AUTH_STEP = "auth"
    TOKEN_STEP = "token"

    form_list = (
        (AUTH_STEP, AuthenticationForm),
        (TOKEN_STEP, BeskAuthenticationTokenForm),
    )

    def get_form_list(self):
        form_list = super().get_form_list()

        # In case we wish to bypass 2FA we should never go to the token step.
        if settings.BYPASS_2FA and self.TOKEN_STEP in form_list:
            del form_list[self.TOKEN_STEP]

        return form_list

    def get_form(self, step=None, data=None, files=None):
        """
        Returns the form for the step. Overwritten because the default method hard-codes
        the form for the token-step as AuthenticationTokenForm instead of
        BeskAuthenticationTokenForm
        """
        if step is None:
            step = self.steps.current

        form_class = self.get_form_list()[step]
        kwargs = self.get_form_kwargs(step)
        kwargs.update(
            {
                "data": data,
                "files": files,
                "prefix": self.get_form_prefix(step, form_class),
                "initial": self.get_form_initial(step),
            }
        )

        return form_class(**kwargs)

    def get_success_url(self):
        return self.back or reverse("suila:root")

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if settings.PUBLIC:
                # MitID login
                response = self.login_mitid(request, *args, **kwargs)
            else:
                # django login
                response = self.login_django(request, *args, **kwargs)
            if response:
                if self.back:
                    response.set_cookie(
                        "back",
                        self.back,
                        secure=True,
                        httponly=True,
                        samesite="None",
                    )
                return response

        backpage = self.request.COOKIES.get("back")
        if backpage:
            return redirect(backpage)
        return redirect("suila:root")

    def login_mitid(self, request, *args, **kwargs) -> HttpResponse | None:
        # Get user from auth data
        user = authenticate(
            request=request,
            saml_data=request.session.get("saml"),
        )
        if user and user.is_authenticated:
            # store user in session
            login(
                request=request,
                user=user,
                backend="django_mitid_auth.saml.backend.Saml2Backend",
            )
        if not request.user.is_authenticated:
            # no user, redirect to login page
            return redirect(reverse("login:mitid:login"))
        return None

    def login_django(self, request, *args, **kwargs) -> HttpResponse | None:
        return super().get(request, *args, **kwargs)

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


class TwoFactorSetup(SetupView):
    form_list = [("method", BeskAuthenticationTokenForm)]

    def get_success_url(self):
        return add_parameters_to_url(
            reverse("suila:root"),
            {"two_factor_success": 1},
        )


class LogoutView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        if settings.PUBLIC and (
            self.request.session.get(BACKEND_SESSION_KEY)
            == "django_mitid_auth.saml.backend.Saml2Backend"
            or "saml" in self.request.session
        ):
            return reverse("login:mitid:logout")
        else:
            logout(self.request)
            return settings.LOGOUT_REDIRECT_URL


def on_session_expired(request: HttpRequest) -> HttpResponse | None:
    if request.path == reverse("login:mitid:logout-callback"):
        return None  # Do not redirect to login
    redirect_url = getattr(settings, "SESSION_TIMEOUT_REDIRECT", None)
    if redirect_url:
        return redirect(redirect_url)
    else:
        return redirect_to_login(next=request.path)
