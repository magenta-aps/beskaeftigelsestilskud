# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from data_analysis.templatetags.bf_tags import concat, get, multiply, urlparams, yesno
from django.template import Context, Engine
from django.test import TestCase
from django.utils.translation import gettext_lazy as _


class TagsTest(TestCase):
    def test_urlparams(self):
        self.assertEqual(urlparams({"foo": "bar", "answer": 42}), "foo=bar&answer=42")
        self.assertEqual(
            Engine.get_default()
            .from_string("{% load bf_tags %}{{ test|urlparams|safe }}")
            .render(Context({"test": {"foo": "bar", "answer": 42}})),
            "foo=bar&answer=42",
        )

    def test_multiply(self):
        self.assertEqual(multiply(1, 2), 2)
        self.assertEqual(multiply(2, 2), 4)
        self.assertEqual(multiply(-2, 2), -4)
        self.assertEqual(multiply(0, 2), 0)

    def test_concat(self):
        self.assertEqual(concat("", ""), "")
        self.assertEqual(concat("a", ""), "a")
        self.assertEqual(concat("", "b"), "b")
        self.assertEqual(concat("abc", "def"), "abcdef")

    def test_get(self):
        self.assertEqual(get({"abc": 123}, "abc"), 123)
        self.assertIsNone(get({"abc": 123}, "bar"))
        self.assertEqual(get({123: 456}, 123), 456)
        self.assertIsNone(get({123: 456}, 456))
        self.assertEqual(get({"123": 456}, 123), 456)
        self.assertIsNone(get({"123": 456}, 456))
        self.assertEqual(get([123, 456], 0), 123)
        self.assertEqual(get([123, 456], 1), 456)
        self.assertIsNone(get([123, 456], 2))
        self.assertEqual(get((123, 456), 0), 123)
        self.assertEqual(get((123, 456), 1), 456)
        self.assertIsNone(get((123, 456), 2))

        class Foo(object):
            def __init__(self, bar):
                self.bar = bar

        self.assertEqual(get(Foo(123), "bar"), 123)
        self.assertIsNone(get(Foo(123), "bøf"))

    def test_yesno(self):
        self.assertEqual(yesno(True), _("Ja"))
        self.assertEqual(yesno(False), _("Nej"))
