# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from data_analysis.forms import HistogramOptionsForm, PersonAnalysisOptionsForm
from django.test import TestCase
from django.urls import reverse

from suila.models import Person, PersonYear, Year


class DataSetupMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person = Person.objects.create()
        cls.year_2020, _ = Year.objects.get_or_create(year=2020)
        cls.year_2021, _ = Year.objects.get_or_create(year=2021)


class TestHistogramOptionsForm(DataSetupMixin, TestCase):
    def test_renders_year_choices(self):
        form = HistogramOptionsForm()
        self.assertListEqual(
            form.fields["year"].choices,
            [
                (self._year_url(2020), 2020),
                (self._year_url(2021), 2021),
            ],
        )

    def _year_url(self, year):
        return reverse("data_analysis:histogram", kwargs={"year": year})


class TestPersonAnalysisOptionsForm(DataSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        PersonYear.objects.get_or_create(person=cls.person, year=cls.year_2020)
        PersonYear.objects.get_or_create(person=cls.person, year=cls.year_2021)

    def test_renders_year_choices(self):
        form = PersonAnalysisOptionsForm(instance=self.person, data={"year": 2020})
        self.assertListEqual(
            form.fields["year_start"].choices,
            [
                (2020, 2020),
                (2021, 2021),
            ],
        )
        self.assertListEqual(
            form.fields["year_end"].choices,
            [
                (2020, 2020),
                (2021, 2021),
            ],
        )
