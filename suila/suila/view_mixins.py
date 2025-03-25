# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from functools import cached_property
from typing import Iterable, List, Optional

from common.models import User
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from suila.model_mixins import PermissionsMixin


class PermissionsRequiredMixin:
    required_object_permissions: List[str] = ["view"]
    required_model_permissions: List[str] = []

    def dispatch(self, request, *args, **kwargs):
        if self.required_model_permissions:
            if not self.has_permissions(
                request=request, required_permissions=self.required_model_permissions
            ):
                raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        object: PermissionsMixin = super().get_object(queryset)
        if len(self.required_object_permissions) > 0:
            if not object.has_object_permissions(
                self.request.user, self.required_object_permissions
            ):
                raise PermissionDenied()
        return object

    @classmethod
    def has_permissions(
        cls,
        user: User | AnonymousUser | None = None,
        request: HttpRequest | None = None,
        required_permissions: Optional[Iterable[str]] = None,
    ) -> bool:
        if user is None:
            if request is None:
                raise ValueError("Must specify either userdata or request")
            user = request.user
        if required_permissions is None:
            required_permissions = cls.required_model_permissions
        return PermissionsMixin.has_model_permissions(user, required_permissions)


class MustHavePersonYearMixin:

    @cached_property
    def must_show_no_year_message(self):
        return not self.get_object().personyear_set.exists()  # type: ignore

    def get_template_names(self):
        if self.must_show_no_year_message:
            return ["suila/person_no_year.html"]
        return super().get_template_names()  # type: ignore

    def get(self, request, *args, **kwargs) -> HttpResponse:
        if self.must_show_no_year_message:
            return self.render_to_response({})  # type: ignore
        return super().get(request, *args, **kwargs)  # type: ignore
