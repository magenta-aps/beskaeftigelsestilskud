from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from prisme.client import Prisme
from prisme.exceptions import PrismeException

from suila.integrations.prisme.client import (
    InvoiceCustomTableResponse,
    SuilaInvoiceRequest,
)


class InvoiceTest(TestCase):

    @override_settings(
        PRISME={
            **settings.PRISME,
            "department_recid": "1000",
        }
    )
    def test_invoice_lines(self):

        lines = self.form.invoice_lines
        self.assertEqual(len(lines), 3)

        harbor_tax_line = lines[0].dict
        self.assertEqual(harbor_tax_line["Description"], "Harbour tax")
        self.assertEqual(harbor_tax_line["Quantity"], 1)
        self.assertEqual(harbor_tax_line["UnitPrice"], "15500000.00")
        self.assertEqual(harbor_tax_line["AmountCur"], "15500000.00")
        self.assertEqual(
            harbor_tax_line["InvoiceTxt"],
            "Upernavik, 2024.05.01 12:00 - 2024.06.01 12:00",
        )
        self.assertEqual(
            harbor_tax_line["ledgerDimensionSegments"],
            {
                "ledgerDimensionSegment": [
                    {"Name": "Afdeling", "Value": "1000"},
                    {"Name": "Finanslov", "Value": 0},
                    {"Name": "Formaal", "Value": "0000000000"},
                    {
                        "Name": "ArtsKontoplan",
                        "Value": "000001111",
                    },
                    {"Name": "Sted", "Value": "001234"},
                ]
            },
        )

        passenger_tax_line = lines[1].dict
        self.assertEqual(passenger_tax_line["Description"], "Passenger tax")
        self.assertEqual(passenger_tax_line["Quantity"], 5000)
        self.assertEqual(passenger_tax_line["UnitPrice"], "10.00")
        self.assertEqual(passenger_tax_line["AmountCur"], "50000.00")
        self.assertEqual(passenger_tax_line["InvoiceTxt"], "5000 passengers")

        disembarkment_tax_line = lines[2].dict
        self.assertEqual(disembarkment_tax_line["Description"], "Disembarkment tax")
        self.assertEqual(disembarkment_tax_line["Quantity"], 1000)
        self.assertEqual(disembarkment_tax_line["UnitPrice"], "20.00")
        self.assertEqual(disembarkment_tax_line["AmountCur"], "20000.00")
        self.assertEqual(
            disembarkment_tax_line["InvoiceTxt"],
            "Hans Ø, 2024.05.01 12:00, 1000 passengers",
        )
        self.assertEqual(
            disembarkment_tax_line["ledgerDimensionSegments"],
            {
                "ledgerDimensionSegment": [
                    {"Name": "Afdeling", "Value": "1000"},
                    {"Name": "Finanslov", "Value": 0},
                    {"Name": "Formaal", "Value": "0000000000"},
                    {
                        "Name": "ArtsKontoplan",
                        "Value": "000002222",
                    },
                    {"Name": "Sted", "Value": "010500"},
                ]
            },
        )

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    @patch.object(Prisme, "process_service")
    def test_send_invoice(self, mock_process_service):
        mock_return = MagicMock()
        mock_return.rec_id = 1
        mock_return.afgift_id = 1
        mock_return.invoice_id = 1
        mock_process_service.side_effect = [
            PrismeException(250, "Debitorkonto findes ikke", {}),
            mock_return,
            mock_return,
        ]
        self.form.submit()
        self.form.send_invoice()
        mock_process_service.assert_called()
        invoice_request = mock_process_service.call_args[0][0]
        self.assertIsInstance(invoice_request, SuilaInvoiceRequest)
        data = invoice_request.dict
        self.assertEqual(data["HarborTaxIdFUJ"], self.form.pk)
        self.assertEqual(len(invoice_request.lines), 3)
        self.assertEqual(
            sum([line.quantity * line.unit_price for line in invoice_request.lines]),
            Decimal("15570000.00"),
        )

    def test_custtable_response(self):
        response = InvoiceCustomTableResponse(
            None,
            """
            <CustTable><AccountNum>1234</AccountNum></CustTable>
            """,
        )
        self.assertEqual(response.account_num, 1234)

    def test_custtable_response_none(self):
        response = InvoiceCustomTableResponse(None, None)
        self.assertFalse(hasattr(response, "account_num"))
