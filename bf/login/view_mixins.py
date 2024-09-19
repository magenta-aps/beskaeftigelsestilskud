# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.contrib.auth.models import AnonymousUser
from django.template.response import TemplateResponse


class LoginRequiredMixin(DjangoLoginRequiredMixin):

    @property
    def two_factor_setup_required(self):
        return TemplateResponse(
            request=self.request,
            status=403,
            template="two_factor/core/otp_required.html",
        )

    def dispatch(self, request, *args, **kwargs):
        if (
            not isinstance(self.request.user, AnonymousUser)
            and not settings.BYPASS_2FA
            and not self.request.user.is_verified()
        ):
            return self.two_factor_setup_required
        return super().dispatch(request, *args, **kwargs)
