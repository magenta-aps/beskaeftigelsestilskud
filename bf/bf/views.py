# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "bf/root.html"
