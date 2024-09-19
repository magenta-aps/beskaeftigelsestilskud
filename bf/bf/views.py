# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.views.generic import TemplateView
from login.view_mixins import LoginRequiredMixin


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "bf/root.html"
