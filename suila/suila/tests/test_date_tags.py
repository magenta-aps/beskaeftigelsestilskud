# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils.translation import override

from suila.models import PrismeBatch, PrismeBatchItem
from suila.templatetags.date_tags import get_payment_date, month_name
from suila.tests.mixins import BaseEnvMixin


class TestMonthName(SimpleTestCase):
    """Test the `suila.templatetags.date_tags.month_name` function."""

    def test_valid_input(self):
        with override("da"):
            self.assertEqual(month_name(5), "Maj")

    def test_invalid_input(self):
        # 1. Test that an invalid key does not raise an error
        self.assertIsNone(month_name(None))  # type: ignore
        # 2. Test that failing to capitalize the month name does not raise an error.
        # Replace `MONTHS` with a dictionary where the value cannot be capitalized.
        with patch("suila.templatetags.date_tags.dates.MONTHS", new=lambda: {0: None}):
            self.assertIsNone(month_name(0))


class TestGetPaymentDate(BaseEnvMixin, TestCase):
    """Test the `suila.templatetags.date_tags.get_payment_date` function."""

    def setUp(self):
        super().setUp()

        self.person_month = self.get_or_create_person_month(
            1,
            import_date=date(self.year.year, 1, 1),
        )

    def test_valid_input(self):
        self.assertEqual(self.year.year, 2020)
        self.assertEqual(self.person_month.month, 1)
        self.assertEqual(get_payment_date(self.person_month), date(2020, 3, 17))

    def test_get_payout_date_from_prisme_item(self):

        prisme_year = str(1991)
        prisme_month = str(2).zfill(2)
        prisme_day = str(7).zfill(2)

        prisme_batch = PrismeBatch.objects.create(
            export_date=datetime.date(2020, 1, 1), status="sent", prefix=1
        )

        PrismeBatchItem.objects.create(
            prisme_batch=prisme_batch,
            person_month=self.person_month,
            invoice_no=f"{0:015d}{12:05d}",
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800000031700&"
                "09+&1002&1100000101001111&"
                f"12{prisme_year}{prisme_month}{prisme_day}&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )

        self.assertEqual(get_payment_date(self.person_month), date(1991, 2, 7))

    def test_get_payout_date_bad_g68_content(self):

        prisme_batch = PrismeBatch.objects.create(
            export_date=datetime.date(2020, 1, 1), status="sent", prefix=1
        )

        PrismeBatchItem.objects.create(
            prisme_batch=prisme_batch,
            person_month=self.person_month,
            invoice_no=f"{0:015d}{12:05d}",
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800000031700&"
                "09+&1002&1100000101001111&"
                # f"12{prisme_year}{prisme_month}{prisme_day}&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )

        # Fallback to _get_payment_date(person_month.year, person_month.month)
        # Because there is no payout date in the g68_content
        self.assertEqual(get_payment_date(self.person_month), date(2020, 3, 17))
