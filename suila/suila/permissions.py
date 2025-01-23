from typing import Set, Tuple

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model


class SuilaPermissionBackend(ModelBackend):
    @staticmethod
    def action(permission: Permission) -> str:
        return permission.codename.split("_")[0]

    def get_all_permissions(self, user_obj, obj=None):
        # Mostly copied from super
        if not user_obj.is_active or user_obj.is_anonymous:
            # Needed to override here, because super would return if obj is not None
            return set()

        if not hasattr(user_obj, "_obj_perm_cache"):
            user_obj._obj_perm_cache = {}
        if obj is None:
            obj_key = "None"
        else:
            obj_key = f"{obj.__class__.__name__}.{obj.pk}"
        if obj_key not in user_obj._obj_perm_cache:
            user_obj._obj_perm_cache[obj_key] = {
                *self.get_user_permissions(user_obj, obj=obj),
                *self.get_group_permissions(user_obj, obj=obj),
            }
        return user_obj._obj_perm_cache[obj_key]

    def _get_permissions(self, user_obj, obj, from_name):
        # Mostly copied from super
        if not user_obj.is_active or user_obj.is_anonymous:
            # Needed to override here, because super would return if obj is not None
            return set()

        if obj is None:
            perm_cache_name = "_%s_perm_cache_%s" % (from_name, obj.__class__.__name__)
        else:
            perm_cache_name = "_%s_perm_cache_%s.%d" % (
                from_name,
                obj.__class__.__name__,
                obj.pk,
            )
        if not hasattr(user_obj, perm_cache_name):
            if user_obj.is_superuser:
                perms = Permission.objects.all()
            else:
                perms = getattr(self, "_get_%s_permissions" % from_name)(user_obj)
            if obj is not None:
                perms = perms.filter(
                    content_type=ContentType.objects.get_for_model(
                        obj.__class__, for_concrete_model=False
                    )
                )
            perms = set(perms.values_list("content_type__app_label", "codename"))
            if obj is not None:
                perms |= self.get_instance_permissions(
                    user_obj, obj, from_name == "group"
                )  # Added this
            setattr(
                user_obj, perm_cache_name, {"%s.%s" % (ct, name) for ct, name in perms}
            )
        return getattr(user_obj, perm_cache_name)

    def get_instance_permissions(
        self, user: User, obj: Model, from_group: bool
    ) -> Set[Tuple[str, str]]:
        if hasattr(obj, "has_permission"):
            content_type = ContentType.objects.get_for_model(
                obj.__class__, for_concrete_model=False
            )
            return {
                (content_type.app_label, permission.codename)
                for permission in Permission.objects.filter(content_type=content_type)
                if obj.has_permission(user, self.action(permission), from_group)
            }
        return set()
