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
        user = self.request.user
        if (
            not isinstance(user, AnonymousUser)
            and not settings.BYPASS_2FA
            and not user.is_verified()
            and (
                user.is_staff
                or user.is_superuser
                or user.groups.filter(
                    name__in=("Borgerservice", "Skattestyrelsen")
                ).exists()
            )
        ):
            return self.two_factor_setup_required
        return super().dispatch(request, *args, **kwargs)
