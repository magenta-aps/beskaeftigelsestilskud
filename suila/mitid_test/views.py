import json

from django.contrib.sessions.models import Session
from django.http.response import HttpResponse
from django.template.response import TemplateResponse
from django.views.generic import TemplateView
from django.views.generic.base import View
from django_mitid_auth import login_provider_class
from django_mitid_auth.saml.mixins import MitIdLOAMixin


class ClearSessionView(View):
    # Rydder brugerens session
    def get(self, request, *args, **kwargs):
        request.session.flush()
        return HttpResponse("Session ryddet")


class PrivilegeView(TemplateView):
    template_name = "mitid_test/dummy.html"
    description = "dummy page"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**{**kwargs, "description": self.description})

    def permission_denied(self, request, *args, **kwargs):
        return TemplateResponse(request, "mitid_test/permission_denied.html")


class Privilege0View(PrivilegeView):
    # SP-åben-side-1
    description = "Side der ikke kræver privilegier"


class Privilege1View(MitIdLOAMixin, PrivilegeView):
    # SP-beskyttet-side-1
    required_level_of_assurance = MitIdLOAMixin.LEVEL_SUBSTANTIAL
    description = "Side der kræver Betydelige privilegier"

    def permission_denied(self, request, *args, **kwargs):
        return TemplateResponse(request, "mitid_test/permission_denied.html")


class Privilege3View(MitIdLOAMixin, PrivilegeView):
    # SP-beskyttet-side-3
    required_level_of_assurance = MitIdLOAMixin.LEVEL_HIGH
    description = "Side der kræver Høje privilegier"

    def permission_denied(self, request, *args, **kwargs):
        return TemplateResponse(request, "mitid_test/permission_denied.html")


class ForceAuthView(View):
    # SP-force-authn-side-1
    def get(self, request):
        request.session["backpage"] = request.GET.get("back")
        provider = login_provider_class()
        request.session["login_method"] = provider.__class__.__name__
        return provider.login(request, auth_params={"force_authn": True})


class ShowSession(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(
            json.dumps({key: value for key, value in request.session.items()}),
            'application/json; charset="utf-8"',
        )


class ListSessions(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(
            json.dumps(
                [
                    {
                        "session_key": session.session_key,
                        "expire_date": str(session.expire_date),
                        "data": {
                            key: value for key, value in session.get_decoded().items()
                        },
                    }
                    for session in Session.objects.all()
                ]
            ),
            'application/json; charset="utf-8"',
        )
