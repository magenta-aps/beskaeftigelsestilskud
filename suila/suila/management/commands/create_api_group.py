# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("name", type=str, default="api")

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(
            name=options["name"],
        )
        group.permissions.add(Permission.objects.get(codename="view_person"))
        group.permissions.add(Permission.objects.get(codename="view_year"))
        group.permissions.add(Permission.objects.get(codename="view_personyear"))
        group.permissions.add(Permission.objects.get(codename="view_personmonth"))
