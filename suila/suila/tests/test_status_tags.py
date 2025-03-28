# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import gettext_lazy as _

from suila.models import Person, PersonMonth, PersonYear, PrismeBatchItem, Year
from suila.templatetags.status_tags import display_status


class TestDisplayStatus(TestCase):
    """Test the `suila.templatetags.status_tags.display_status` function."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        person, _ = Person.objects.update_or_create(cpr="0101011111")
        year, _ = Year.objects.update_or_create(year=2020)
        person_year, _ = PersonYear.objects.update_or_create(person=person, year=year)
        cls.person_month, _ = PersonMonth.objects.update_or_create(
            person_year=person_year,
            month=1,
            import_date=datetime.date(2020, 1, 1),
        )

    def test_prisme_batch_item_status_used_if_present(self):
        # Arrange: add a Prisme batch item to the person month under test
        self.person_month.prismebatchitem = PrismeBatchItem(
            status=PrismeBatchItem.PostingStatus.Posted
        )
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(
            result,
            {"name": PrismeBatchItem.PostingStatus.Posted.label, "established": True},
        )

    @patch("suila.templatetags.status_tags.datetime", wraps=datetime)
    def test_before_current_month(self, mock_datetime):
        # Arrange: set current time to before the year and month of the person month
        # under test.
        mock_datetime.date.today.return_value = datetime.date(2019, 12, 31)
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(
            result, {"name": _("Foreløbigt beløb"), "established": False}
        )

    @patch("suila.templatetags.status_tags.datetime", wraps=datetime)
    def test_after_current_month(self, mock_datetime):
        # Arrange: set current time to the year and month of the person month under test
        mock_datetime.date.today.return_value = datetime.date(2020, 1, 1)
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(result, {"name": _("Beløb fastlagt"), "established": True})
