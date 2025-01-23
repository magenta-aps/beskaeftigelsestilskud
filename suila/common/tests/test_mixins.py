from typing import Any, Dict, Tuple

from common.models import User
from django.contrib.auth.models import AnonymousUser
from django.template.response import TemplateResponse
from django.test import RequestFactory
from django.views.generic import TemplateView


class TestViewMixin:

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.request_factory = RequestFactory()
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="admin"
        )
        cls.normal_user = User.objects.create_user(
            username="borger", password="borger", cpr="0101011111"
        )
        cls.no_user = AnonymousUser()

    def view(self, user: User = None, path: str = "", **params: Any) -> TemplateView:
        if user is None:
            user = self.admin_user
        request = self.request_factory.get(path)
        request.user = user
        view = self.view_class()
        view.setup(request, **params)
        return view

    def request_get(
        self, user: User = None, path: str = "", **params: Any
    ) -> Tuple[TemplateView, TemplateResponse]:
        view = self.view(user, path, **params)
        response = view.dispatch(view.request, **params)
        return view, response

    def request_post(
        self, user: User = None, path: str = "", data: Dict[str, Any] | None = None
    ) -> Tuple[TemplateView, TemplateResponse]:
        if user is None:
            user = self.admin_user
        if data is None:
            data = {}
        request = self.request_factory.post(path, data)
        request.user = user
        view = self.view_class()
        view.setup(request)
        response = view.dispatch(request, **data)
        return view, response
