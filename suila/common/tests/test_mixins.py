# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Any, Dict, Tuple

from common.models import User
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.template.response import TemplateResponse
from django.test import RequestFactory
from django.views.generic import TemplateView


class UserMixin:

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.request_factory = RequestFactory()
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="admin"
        )

        # Bruger med rettigheder
        cls.staff_user = User.objects.create_user(username="staff", password="staff")
        cls.staff_group = Group.objects.create(name="staff")
        cls.staff_group.permissions.add(
            *Permission.objects.filter(codename__startswith="view")
        )
        cls.staff_user.groups.add(cls.staff_group)

        # Bruger der matcher et CPR-nummer i databasen
        cls.normal_user = User.objects.create_user(
            username="borger1", password="borger1", cpr="0101011111"
        )
        # Bruger der ikke matcher et CPR-nummer
        cls.other_user = User.objects.create_user(
            username="borger2", password="borger2", cpr="9999999999"
        )
        cls.no_user = AnonymousUser()


class TestViewMixin(UserMixin):

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
        self,
        user: User = None,
        path: str = "",
        data: Dict[str, Any] | None = None,
        **params: Any,
    ) -> Tuple[TemplateView, TemplateResponse]:
        if user is None:
            user = self.admin_user
        if data is None:
            data = {}
        request = self.request_factory.post(path, data)
        request.user = user
        view = self.view_class()
        view.setup(request, **params)
        response = view.dispatch(request, **data)
        return view, response
