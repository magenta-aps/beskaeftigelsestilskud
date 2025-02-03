# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from suila.context_processors import person_context
from suila.models import Person, User


class TestPersonContext(TestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def test_person_context_authenticated_with_cpr(self):
        user = User(cpr="0101012222")
        context = self._get_context_for_user(user)
        self.assertIn("person", context)
        self.assertIsInstance(context["person"], Person)
        self.assertEqual(context["person"].cpr, user.cpr)

    def test_person_context_authenticated_without_cpr(self):
        user = User()  # blank CPR
        context = self._get_context_for_user(user)
        self.assertEqual(context, {})

    def test_person_context_anonymous_user(self):
        user = AnonymousUser()
        context = self._get_context_for_user(user)
        self.assertEqual(context, {})

    def _get_context_for_user(self, user) -> dict:
        request = self.factory.get("/")
        request.user = user
        context = person_context(request)
        return context
