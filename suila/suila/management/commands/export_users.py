# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

User = get_user_model()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file", type=str)

    def handle(self, *args, **options):
        user_dicts = []
        for user in User.objects.all():
            user_dict = dict(
                [
                    (f.attname, getattr(user, f.attname))
                    for f in user._meta.get_fields()
                    if hasattr(f, "attname")
                ]
            )
            user_dict["groups"] = [group.name for group in user_dict["groups"].all()]
            user_dict["user_permissions"] = [
                permission.codename
                for permission in user_dict["user_permissions"].all()
            ]
            user_dicts.append(user_dict)
        with open(options["file"], "w", encoding="utf-8") as fp:
            json.dump(user_dicts, fp, cls=DjangoJSONEncoder)
