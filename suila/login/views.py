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
        return redirect("suila:root")

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
        if (
            self.request.session.get(BACKEND_SESSION_KEY)
            == "django_mitid_auth.saml.backend.Saml2Backend"
            or "saml" in self.request.session
        ):
            return reverse("login:mitid:logout")
        else:
            logout(self.request)
            return settings.LOGOUT_REDIRECT_URL
