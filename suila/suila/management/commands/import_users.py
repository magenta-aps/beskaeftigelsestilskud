# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
from datetime import datetime

from common.utils import omit
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

User = get_user_model()


def custom_decoder(obj):
    if "date_joined" in obj:
        obj["date_joined"] = datetime.fromisoformat(obj["date_joined"])
    return obj


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file", type=str)

    def handle(self, *args, **options):
        groups = {g.name: g for g in Group.objects.all()}
        permissions = {p.codename: p for p in Permission.objects.all()}
        with open(options["file"], "r") as fp:
            user_dicts = json.load(fp, object_hook=custom_decoder)
            for user_dict in user_dicts:
                flat_dict = omit(user_dict, "groups", "user_permissions")
                u, _ = User.objects.update_or_create(
                    username=user_dict["username"], defaults=flat_dict
                )
                for group in user_dict["groups"]:
                    u.groups.add(groups[group])
                for permission in user_dict["user_permissions"]:
                    u.user_permissions.add(permissions[permission])
