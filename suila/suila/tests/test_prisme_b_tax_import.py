# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.test.utils import override_settings

from suila.integrations.prisme.b_tax import BTaxPayment, BTaxPaymentImport
from suila.models import BTaxPayment as BTaxPaymentModel
from suila.models import PersonMonth
from suila.tests.helpers import ImportTestCase

_EXAMPLE_1 = "BTAX;3112700000;;2021;-3439;2000004544;3439;2021/04/20;004"
_EXAMPLE_2 = "BTAX;3112710000;;2021;-3439;2000004544;3439;2021/04/20;004"
_EXAMPLE_3 = "BTAX;3112720000;;2021;0;2000004544;3439;2021/04/20;004"


class TestBTaxPayment(SimpleTestCase):
    def test_from_csv_row(self):
        obj = BTaxPayment.from_csv_row(_EXAMPLE_1.split(";"))
        self.assertEqual(obj.type, "BTAX")
        self.assertEqual(obj.cpr, "3112700000")
        self.assertEqual(obj.tax_year, 2021)
        self.assertEqual(obj.amount_paid, -3439)
        self.assertEqual(obj.serial_number, 2000004544)
        self.assertEqual(obj.amount_charged, 3439)
        self.assertEqual(obj.date_charged, date(2021, 4, 20))
        self.assertEqual(obj.rate_number, 4)


class TestBTaxPaymentImport(ImportTestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person_month = cls.add_person_month(311270_0000, 2021, 4)

    def test_import_b_tax(self):
        # Arrange
        instance = BTaxPaymentImport()
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2, _EXAMPLE_3):
            # Act
            objs: list[BTaxPaymentModel] = instance.import_b_tax(MagicMock(), 1)
        # Assert: a `BTaxPayment` object is created for:
        # * `_EXAMPLE_1` (whose CPR, etc. match `self.person_month`)
        # * `_EXAMPLE_2` (whose CPR, etc. does not match an existing `PersonMonth`)
        # * `_EXAMPLE_3` (whose CPR, etc. does not match an existing `PersonMonth`, and
        #   whose `amout_paid` is zero.)
        self.assertQuerySetEqual(
            BTaxPaymentModel.objects.order_by("pk").values(
                "pk",
                "person_month",
                "amount_charged",
                "amount_paid",
                "date_charged",
                "rate_number",
                "serial_number",
            ),
            [
                # `PersonMonth` already exists
                {
                    "pk": objs[0].pk,
                    "person_month": self.person_month.pk,
                    "amount_charged": Decimal(3439),
                    "amount_paid": Decimal(3439),
                    "date_charged": date(2021, 4, 20),
                    "rate_number": 4,
                    "serial_number": 2000004544,
                },
                # `PersonMonth` is created during `BTaxPayment` import
                {
                    "pk": objs[1].pk,
                    "person_month": PersonMonth.objects.get(
                        person_year__person__cpr="3112710000",
                        person_year__year__year=2021,
                        month=4,
                    ).pk,
                    "amount_charged": Decimal(3439),
                    "amount_paid": Decimal(3439),
                    "date_charged": date(2021, 4, 20),
                    "rate_number": 4,
                    "serial_number": 2000004544,
                },
                # No `PersonMonth` is created during `BTaxPayment` import, as the
                # `amount_paid` is zero.
                {
                    "pk": objs[2].pk,
                    "person_month": None,
                    "amount_charged": Decimal(3439),
                    "amount_paid": Decimal(0),
                    "date_charged": date(2021, 4, 20),
                    "rate_number": 4,
                    "serial_number": 2000004544,
                },
            ],
        )

    def test_import_b_tax_is_idempotent(self):
        # Arrange
        instance = BTaxPaymentImport()
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2, _EXAMPLE_3):
            # Act: import the same set of files twice
            instance.import_b_tax(MagicMock(), 1)
            instance.import_b_tax(MagicMock(), 1)

    def test_import_b_tax_verbosity_2(self):
        # Arrange
        stdout = MagicMock()
        instance = BTaxPaymentImport()
        with self.mock_sftp_server(_EXAMPLE_1, _EXAMPLE_2):
            # Act
            instance.import_b_tax(stdout, 2)
        # Assert
        self.assertEqual(stdout.write.call_count, 5)

    @override_settings(PRISME={"b_tax_folder": "foo"})
    def test_get_remote_folder_name(self):
        # Arrange
        instance = BTaxPaymentImport()
        # Act and assert
        self.assertEqual(instance.get_remote_folder_name(), "foo")

    def test_parse(self):
        # Arrange
        instance = BTaxPaymentImport()
        with self.mock_sftp_server(_EXAMPLE_1):
            # Act
            result: list[BTaxPayment] = instance._parse("filename1.csv")
            # Assert
            self.assertIsInstance(result, list)
            self.assertIsInstance(result[0], BTaxPayment)
