# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from bf.templatetags.nav_tags import is_current_url


class TestIsCurrentUrl(SimpleTestCase):
    """Test the `bf.nav_tags.is_current_url` function."""

    def setUp(self):
        super().setUp()
        request_factory = RequestFactory()
        self.request = request_factory.get(
            reverse("bf:person_detail", kwargs={"pk": 0})
        )

    def test_is_current_url_returns_active(self):
        """`is_current_url` should return `active` if specified view is active"""
        self.assertEqual(is_current_url(self.request, "bf:person_detail"), "active")

    def test_is_current_url_returns_empty_string(self):
        """`is_current_url` should return `` if specified view is not active"""
        self.assertEqual(is_current_url(self.request, "bf:person_detail_benefits"), "")
