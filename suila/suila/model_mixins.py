from typing import Iterable, List

from common.models import User
from django.db.models import QuerySet


class PermissionsMixin:

    @classmethod
    def permission_name(cls, action: str) -> str:
        return f"suila.{action}_{cls._meta.model_name}"

    @classmethod
    def filter_user_permissions(cls, qs: QuerySet, user: User, action: str) -> QuerySet:
        if user.is_anonymous or not user.is_active:
            return qs.none()
        if user.is_superuser:
            return qs
        if user.has_perm(cls.permission_name(action), None):
            # User has permission for all instances through
            # the standard Django permission system
            return qs

        qs1 = cls._filter_user_permissions(qs, user, action)
        if qs1 is not None:
            # User has permission to these specific instances
            return qs1
        return qs.none()

    @classmethod
    def _filter_user_permissions(
        cls, qs: QuerySet, user: User, action: str
    ) -> QuerySet | None:
        return qs.none()

    @staticmethod
    def has_model_permissions(
        user: User,
        required_permissions: Iterable[str],
    ) -> bool:
        if user.is_anonymous or not user.is_active:
            return False
        if user.is_superuser:
            return True
        return set(required_permissions).issubset(user.get_all_permissions())

    def has_object_permissions(
        self, user: User, actions: List[str], from_group: bool = False
    ) -> bool:
        if len(actions) == 0:
            raise ValueError("Must specify actions to query permissions for")
        if user.is_anonymous or not user.is_active:
            return False
        if user.is_superuser:
            return True
        for action in actions:
            if user.has_perm(self.permission_name(action), None):
                # User has permission for all instances through
                # the standard Django permission system
                pass
            elif self._has_permission(user, action, from_group):
                # User has permission to this specific instance
                pass
            else:
                return False
        return True

    def _has_permission(self, user: User, action: str, from_group: bool) -> bool:
        return (
            not from_group
            and self.filter_user_permissions(
                self.__class__.objects.filter(pk=self.pk), user, action  # type: ignore
            ).exists()
        )
