# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from data_analysis.templatetags.bf_tags import urlparams
from django.template import Context, Engine
from django.test import TestCase


class TagsTest(TestCase):
    def test_urlparams(self):
        self.assertEqual(urlparams({"foo": "bar", "answer": 42}), "foo=bar&answer=42")
        self.assertEqual(
            Engine.get_default()
            .from_string("{% load bf_tags %}{{ test|urlparams|safe }}")
            .render(Context({"test": {"foo": "bar", "answer": 42}})),
            "foo=bar&answer=42",
        )
