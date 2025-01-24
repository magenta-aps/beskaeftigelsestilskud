from typing import Iterable, List, Optional

from common.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

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
        user: User | None = None,
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
