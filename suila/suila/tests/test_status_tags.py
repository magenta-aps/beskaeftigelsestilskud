# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import gettext_lazy as _

from suila.models import (
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatchItem,
    TaxScope,
    Year,
)
from suila.templatetags.amount_tags import display_amount
from suila.templatetags.status_tags import display_status, format_tax_scope


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
        self.person_month.benefit_transferred = 123
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(
            result,
            {"name": PrismeBatchItem.PostingStatus.Posted.label, "established": True},
        )

        # If the amount equals zero - we should always display "Beløb fastlagt"
        self.person_month.benefit_transferred = 0
        self.person_month.save()

        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(result, {"name": "Beløb fastlagt", "established": True})

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

    def test_paused(self):
        # Arrange: add a Prisme batch item to the person month under test
        self.person_month.prismebatchitem = PrismeBatchItem(
            status=PrismeBatchItem.PostingStatus.Posted, paused=True
        )
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(
            result,
            {"name": _("Udbetalingspause"), "established": True},
        )

    @patch("suila.templatetags.status_tags.datetime", wraps=datetime)
    @patch("suila.models.PersonMonth.paused")
    def test_paused_after_current_month(self, mock_datetime, paused_mock):
        paused_mock.return_value = True
        # Arrange: set current time to the year and month of the person month under test
        mock_datetime.date.today.return_value = datetime.date(2020, 1, 1)
        # Act
        result = display_status(self.person_month)
        # Assert
        self.assertDictEqual(
            result, {"name": _("Udbetalingspause"), "established": True}
        )


class TestDisplayTaxScope(TestCase):

    def test_format_tax_scope(self):
        self.assertEqual(
            format_tax_scope(TaxScope.FULDT_SKATTEPLIGTIG), "Fuld skattepligtig"
        )

        self.assertEqual(
            format_tax_scope(TaxScope.DELVIST_SKATTEPLIGTIG), "Delvist skattepligtig"
        )
        self.assertEqual(
            format_tax_scope(TaxScope.FORSVUNDET_FRA_MANDTAL), "Ikke i mandtal"
        )

        self.assertEqual(format_tax_scope("foo"), "")


class TestDisplayAmount(TestCase):
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
            benefit_calculated=123,
            benefit_transferred=456,
        )

    def test_amount_with_prisme_item(self):
        self.assertEqual(display_amount(self.person_month)["value"], "123 kr.")
        self.person_month.prismebatchitem = PrismeBatchItem(
            status=PrismeBatchItem.PostingStatus.Posted
        )
        self.assertEqual(display_amount(self.person_month)["value"], "456 kr.")
