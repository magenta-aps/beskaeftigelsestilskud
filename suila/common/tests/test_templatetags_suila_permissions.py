# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import patch

from common.templatetags.suila_permissions import has_permissions
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

User = get_user_model()


class TestHasPermissions(SimpleTestCase):
    """Verify the behavior of the `suila_permissions.has_permissions` template filter"""

    def setUp(self):
        super().setUp()
        self.user = User()

    @patch.object(User, "has_perm")
    def test_multiple_permission_names(self, mock_has_perm):
        # Act: use template filter with multiple permission names (comma-separated)
        has_permissions(self.user, "a,b,c")
        # Assert: each permission name is tested against our mock `User.has_perm`
        self.assertListEqual(
            [call.args[0] for call in mock_has_perm.call_args_list],
            ["a", "b", "c"],
        )
