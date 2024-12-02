# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from bf.integrations.prisme.b_tax import BTaxPayment, BTaxPaymentImport
from bf.models import BTaxPayment as BTaxPaymentModel
from bf.tests.helpers import ImportTestCase

_EXAMPLE = "BTAX;3112700000;;2021;-3439;2000004544;3439;2021/04/20;004"


class TestBTaxPayment(SimpleTestCase):
    def test_from_csv_row(self):
        obj = BTaxPayment.from_csv_row(_EXAMPLE.split(";"))
        self.assertEqual(obj.type, "BTAX")
        self.assertEqual(obj.cpr, 311270_0000)
        self.assertEqual(obj.tax_year, 2021)
        self.assertEqual(obj.amount_paid, -3439)
        self.assertEqual(obj.serial_number, 2000004544)
        self.assertEqual(obj.amount_charged, 3439)
        self.assertEqual(obj.date_charged, date(2021, 4, 20))
        self.assertEqual(obj.rate_number, 4)


class TestBTaxPaymentImport(ImportTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person_month = cls.add_person_month(311270_0000, 2021, 4)

    def test_import_b_tax(self):
        # Arrange
        instance = BTaxPaymentImport(2021, 4)
        with self.mock_sftp_server(_EXAMPLE):
            # Act
            instance.import_b_tax(MagicMock(), 1)
        # Assert
        self.assertQuerySetEqual(
            BTaxPaymentModel.objects.values("person_month", "filename", "rate_number"),
            [
                {
                    "person_month": self.person_month.pk,
                    "filename": "filename1.csv",
                    "rate_number": 4,
                },
            ],
        )

    def test_import_b_tax_verbosity_2(self):
        # Arrange
        stdout = MagicMock()
        instance = BTaxPaymentImport(2021, 4)
        with self.mock_sftp_server(_EXAMPLE):
            # Act
            instance.import_b_tax(stdout, 2)
        # Assert
        self.assertEqual(stdout.write.call_count, 4)
