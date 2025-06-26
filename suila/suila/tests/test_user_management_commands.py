# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase


class TestImportExport(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("create_groups")
        call_command("create_user", "user1", "pw")
        call_command("create_user", "user2", "pw", is_staff=True)
        call_command("create_user", "user3", "pw", is_superuser=True)
        call_command("create_user", "user4", "pw", groups=["Borgerservice"])
        call_command("create_user", "user5", "pw", cert_subject="foo")

        User = get_user_model()
        user1 = User.objects.get(username="user1")

        user1.user_permissions.add(
            Permission.objects.get(codename="view_data_analysis")
        )
        user1.save()

    def test_user_is_created(self):
        self.assertIn("user1", [u.username for u in get_user_model().objects.all()])

    def test_import_export(self):
        User = get_user_model()
        self.assertEqual(User.objects.all().count(), 5)

        call_command("export_users", "/tmp/users.json")
        self.assertIn("users.json", os.listdir("/tmp"))

        User.objects.all().delete()

        self.assertEqual(User.objects.all().count(), 0)
        call_command("import_users", "/tmp/users.json")
        self.assertEqual(User.objects.all().count(), 5)

    def test_create_user_nonexisting_group(self):
        stdout = StringIO()
        call_command(
            "create_user", "user4", "pw", groups=["McDonalds employees"], stdout=stdout
        )
        self.assertIn("Group McDonalds employees does not exist", stdout.getvalue())
