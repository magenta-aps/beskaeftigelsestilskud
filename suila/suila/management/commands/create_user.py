# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument("password", type=str)
        parser.add_argument("-s", "--is_staff", action="store_true")
        parser.add_argument("-S", "--is_superuser", action="store_true")
        parser.add_argument("-g", "--groups", type=str, nargs="+")
        parser.add_argument("-c", "--cert-subject", type=str)

    def handle(self, *args, **options):
        name = options["username"].capitalize()
        user, _ = User.objects.update_or_create(
            username=options["username"],
            defaults={
                "is_staff": options["is_staff"],
                "is_superuser": options["is_superuser"],
                "first_name": name,
                "last_name": f"{name}sen",
            },
        )
        password = options["password"]
        if password and not user.check_password(password):
            user.set_password(password)
            user.save()
        groups = options.get("groups")
        if groups:
            for group_name in groups:
                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    self.stdout.write(f"Group {group_name} does not exist")
        cert_subject = options.get("cert_subject")
        if cert_subject:
            user.cert_subject = cert_subject
            user.save()
