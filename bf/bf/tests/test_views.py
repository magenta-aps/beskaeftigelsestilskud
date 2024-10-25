# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.test import TestCase
from django.utils.translation import gettext_lazy as _

from bf.models import Person
from bf.views import CategoryChoiceFilter


class TestCategoryChoiceFilter(TestCase):

    def setUp(self):
        super().setUp()
        self.instance = CategoryChoiceFilter(
            field_name="location_code",
            field=Person.location_code,
        )
        self.person1 = Person.objects.update_or_create(cpr=1, location_code=1)
        self.person2 = Person.objects.update_or_create(cpr=2, location_code=1)
        self.person3 = Person.objects.update_or_create(cpr=3, location_code=None)

    def test_choices(self):
        self.assertListEqual(
            # self.instance.extra["choices"] is a callable
            self.instance.extra["choices"](),
            [
                # 2 persons have location code "1"
                ("1", "1 (2)"),
                # 1 person has no location code
                (CategoryChoiceFilter._isnull, f"{_('Ingen')} (1)"),
            ],
        )

    def test_filter_on_isnull(self):
        filtered_qs = self.instance.filter(
            Person.objects.all(), CategoryChoiceFilter._isnull
        )
        self.assertQuerySetEqual(
            filtered_qs,
            Person.objects.filter(location_code__isnull=True),
        )
