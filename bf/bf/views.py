from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class RootView(LoginRequiredMixin, TemplateView):
    template_name = "bf/root.html"
