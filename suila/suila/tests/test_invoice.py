# SPDX-FileCopyrightText: 2026 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from prisme.client import Prisme

from suila.integrations.prisme.client import (
    PrismeClient,
    SuilaInvoiceRequest,
    SuilaInvoiceResponse,
)
from suila.models import AnnualIncome, FinalSettlement, Person, PersonYear, Year


class InvoiceTest(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with (
            patch.object(
                FinalSettlement,
                "result",
                new_callable=PropertyMock,
                return_value=Decimal("-1234.56"),
            ),
            patch.object(
                FinalSettlement, "pdf", new_callable=PropertyMock, return_value=None
            ),
        ):
            cls.final_settlement = FinalSettlement.objects.create(
                annual_income=AnnualIncome.objects.create(
                    person_year=PersonYear.objects.create(
                        person=Person.objects.create(
                            cpr="1234567890",
                        ),
                        year=Year.objects.create(
                            year=2026,
                        ),
                    )
                ),
                _result=Decimal("1234.56"),
            )

    @staticmethod
    def strip_whitespace(string):
        return "".join(string.split())

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    def test_prismeclient_idempotent(self):
        client1 = PrismeClient.from_settings()
        client2 = PrismeClient.from_settings()
        self.assertEqual(client1, client2)

    @override_settings(PRISME={**settings.PRISME, "mock": True})
    def test_prismeclient_mock(self):
        PrismeClient.instance = None
        try:
            client = PrismeClient.from_settings()
            self.assertTrue(client.mock)
            self.assertEqual(client.wsdl_file, "")
        finally:
            PrismeClient.instance = None

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    def test_prismeclient_multiple_returns(self):
        with (
            patch.object(
                Prisme,
                "process_service",
                return_value=[
                    SuilaInvoiceResponse(
                        None,
                        "<CustInvoiceTable><RecId>111</RecId>"
                        "<InvoiceId>222</InvoiceId></CustInvoiceTable>",
                    ),
                    SuilaInvoiceResponse(
                        None,
                        "<CustInvoiceTable><RecId>333</RecId>"
                        "<InvoiceId>444</InvoiceId></CustInvoiceTable>",
                    ),
                ],
            ),
            patch("suila.integrations.prisme.client.logger.warning") as mock_log,
        ):
            client = PrismeClient.from_settings()
            response = client.process_service(None)
            self.assertEqual(response.rec_id, "111")
            mock_log.assert_called_with(
                "Multiple responses returned from Prisme. Expected 1, got 2:\n"
                "<CustInvoiceTable><RecId>111</RecId><InvoiceId>222</InvoiceId>"
                "</CustInvoiceTable>\n<CustInvoiceTable><RecId>333</RecId>"
                "<InvoiceId>444</InvoiceId></CustInvoiceTable>"
            )

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    def test_send_invoice_nonnegative(self):
        with (
            patch.object(Prisme, "process_service") as mock_process_service,
            patch.object(
                FinalSettlement,
                "result",
                new_callable=PropertyMock,
                return_value=Decimal("1234.56"),
            ),
            patch.object(
                FinalSettlement, "pdf", new_callable=PropertyMock, return_value=None
            ),
        ):
            mock_return = MagicMock()
            mock_return.rec_id = 1
            mock_return.afgift_id = 1
            mock_return.invoice_id = 1

            self.final_settlement.send_invoice(
                client=PrismeClient.from_settings(),
                accounting_date=date(2026, 9, 15),
                due_date=date(2026, 9, 20),
                invoice_date=date(2026, 9, 25),
            )
            mock_process_service.assert_not_called()

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    def test_send_invoice_already_sent(self):
        with (
            patch.object(Prisme, "process_service") as mock_process_service,
            patch.object(
                FinalSettlement,
                "result",
                new_callable=PropertyMock,
                return_value=Decimal("-1234.56"),
            ),
            patch.object(
                FinalSettlement, "pdf", new_callable=PropertyMock, return_value=None
            ),
        ):
            self.final_settlement.invoice_sent = True
            self.final_settlement.save(update_fields=("invoice_sent",))
            mock_return = MagicMock()
            mock_return.rec_id = 1
            mock_return.afgift_id = 1
            mock_return.invoice_id = 1

            self.final_settlement.send_invoice(
                client=PrismeClient.from_settings(),
                accounting_date=date(2026, 9, 15),
                due_date=date(2026, 9, 20),
                invoice_date=date(2026, 9, 25),
            )
            mock_process_service.assert_not_called()

    @override_settings(PRISME={**settings.PRISME, "mock": False})
    def test_send_invoice(self):
        with (
            patch.object(Prisme, "process_service") as mock_process_service,
            patch.object(
                FinalSettlement,
                "result",
                new_callable=PropertyMock,
                return_value=Decimal("-1234.56"),
            ),
            patch.object(
                FinalSettlement, "pdf", new_callable=PropertyMock, return_value=None
            ),
        ):
            mock_return = MagicMock()
            mock_return.rec_id = 1
            mock_return.afgift_id = 1
            mock_return.invoice_id = 1

            self.final_settlement.send_invoice(
                client=PrismeClient.from_settings(),
                accounting_date=date(2026, 9, 15),
                due_date=date(2026, 9, 20),
                invoice_date=date(2026, 9, 25),
            )

            mock_process_service.assert_called()
            invoice_request = mock_process_service.call_args[0][0]
            self.assertIsInstance(invoice_request, SuilaInvoiceRequest)
            self.assertEqual(len(invoice_request.lines), 1)
            self.assertEqual(
                sum(
                    [line.quantity * line.unit_price for line in invoice_request.lines]
                ),
                Decimal("1234.56"),
            )
            self.assertEqual(
                self.strip_whitespace(invoice_request.xml),
                self.strip_whitespace(
                    """
                <custinvoicetable>
                  <AccountingDate>2026-09-15T00:00:00</AccountingDate>
                  <ContactPersonId>SEL-005486</ContactPersonId>
                  <CurrencyCode>DKK</CurrencyCode>
                  <DueDate>2026-09-20T00:00:00</DueDate>
                  <EinvoiceEANNum>5701234012344</EinvoiceEANNum>
                  <InvoiceDate>2026-09-25T00:00:00</InvoiceDate>
                  <InvoiceIntroTxt>SUILA</InvoiceIntroTxt>
                  <LedgerYear></LedgerYear>
                  <OMDepartmentRecIdExtFUJ>5637153652</OMDepartmentRecIdExtFUJ>
                  <PurchOrderFormNum>Bins</PurchOrderFormNum>
                  <custTable>
                    <CustGroup>210026</CustGroup>
                    <IdentificationNumber>1234567890</IdentificationNumber>
                  </custTable>
                  <custinvoiceLines>
                    <custinvoiceLine>
                      <AmountCur>1234.56</AmountCur>
                      <Beneficiary>1234567890</Beneficiary>
                      <Description>SUILA 2026</Description>
                      <InvoiceTxt>Suila-tapit 2026</InvoiceTxt>
                      <ProjCategoryId>1</ProjCategoryId>
                      <Project>Suila</Project>
                      <Quantity>1</Quantity>
                      <UnitPrice></UnitPrice>
                      <ledgerDimensionSegments>
                        <ledgerDimensionSegment>
                          <Name>Afdeling</Name>
                          <Value>12345</Value>
                        </ledgerDimensionSegment>
                        <ledgerDimensionSegment>
                          <Name>Finanslov</Name>
                          <Value>2222</Value>
                        </ledgerDimensionSegment>
                        <ledgerDimensionSegment>
                          <Name>Formaal</Name>
                          <Value>0000003333</Value>
                        </ledgerDimensionSegment>
                        <ledgerDimensionSegment>
                          <Name>ArtsKontoplan</Name>
                          <Value>000004444</Value>
                        </ledgerDimensionSegment>
                        <ledgerDimensionSegment>
                          <Name>Sted</Name>
                          <Value>019000</Value>
                        </ledgerDimensionSegment>
                      </ledgerDimensionSegments>
                    </custinvoiceLine>
                  </custinvoiceLines>
                  <files>
                    <file></file>
                  </files>
                </custinvoicetable>
                """
                ),
            )

    def test_response(self):
        response = SuilaInvoiceResponse(
            None,
            """
            <CustInvoiceTable><RecId>1234</RecId><InvoiceId>5678</InvoiceId></CustInvoiceTable>
            """,
        )
        self.assertEqual(response.rec_id, "1234")
        self.assertEqual(response.invoice_id, "5678")

    def test_response_fail(self):
        response = SuilaInvoiceResponse(
            None,
            None,
        )
        self.assertIsNone(response.rec_id)
        self.assertIsNone(response.invoice_id)
