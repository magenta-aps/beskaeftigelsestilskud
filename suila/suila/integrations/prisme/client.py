import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

from django.conf import settings
from django.core.files import File
from prisme.client import Prisme
from prisme.file import File as InvoiceFile
from prisme.invoice import InvoiceLine, InvoiceRequest, InvoiceResponse
from prisme.request import ResponseType


class SuilaInvoiceLine(InvoiceLine):
    def __init__(
        self,
        description: str,
        quantity: int,
        unit_price: int | Decimal,
        text: str,
        locality_code: int | str,
        beneficiary: int | str,
    ):
        prisme_settings = settings.PRISME  # type: ignore[misc]
        super().__init__(
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            text=text,
            ledger_dimension={
                "Afdeling": prisme_settings["department_recid"],
                "Finanslov": prisme_settings["finance_law_id"],
                "Formaal": str(prisme_settings["purpose_id"]).zfill(10),
                "ArtsKontoplan": str(prisme_settings["type_account_plan_id"]).zfill(9),
                "Sted": str(locality_code).zfill(6),
            },
            beneficiary=str(beneficiary),
            project=prisme_settings["project_name"],
            project_category=prisme_settings["project_category_id"],
        )


class SuilaInvoiceRequest(InvoiceRequest):
    def __init__(
        self,
        invoice_date: datetime | date,
        due_date: datetime | date,
        accounting_date: datetime | date,
        text: str,
        files: List[File],
        lines: List[SuilaInvoiceLine],
        cpr: str | int,
        year: int,
    ):
        prisme_settings = settings.PRISME  # type: ignore[misc]
        super().__init__(
            currency_code=prisme_settings["currency_code"],
            department_recid=prisme_settings["department_recid_ext"],
            invoice_ean=prisme_settings["invoice_ean"],
            order_form_num=prisme_settings["order_form_num"],
            contact_person_id=prisme_settings["contact_person_id"],
            invoice_date=invoice_date,
            due_date=due_date,
            accounting_date=accounting_date,
            text=text,
            files=[
                InvoiceFile(
                    # TODO: Hvilken fil skal med?
                    name=os.path.basename(file.name),
                    path=os.path.join(
                        settings.STORAGE_PDF, file.name  # type: ignore[misc]
                    ),
                )
                for file in files
                if file.name
            ],
            lines=lines,
        )
        self.cpr = cpr

        self.customer_group = f"2100{str(year)[-2:]}"

    @property
    def dict(self) -> Dict[str, str | int | datetime | Dict[str, List[dict]]]:
        d = super().dict
        d["custTable"] = {
            "IdentificationNumber": self.cpr,
            "CustGroup": self.customer_group,
        }
        return d

    def create_custom_table_request(self) -> "InvoiceCustomTableRequest":
        request = InvoiceCustomTableRequest(
            invoice_date=self.invoice_date,
            due_date=self.due_date,
            accounting_date=self.accounting_date,
            text=self.text,
            lines=self.lines,
            files=[],
            cpr=self.cpr,
        )
        request.files = self.files
        return request

    @classmethod
    def response_class(cls) -> type[ResponseType]:
        return SuilaInvoiceResponse  # pragma: no cover


class InvoiceCustomTableResponse(InvoiceResponse):
    def __init__(self, request: SuilaInvoiceRequest, xml: str):
        super().__init__(request, xml)
        if self.data is not None:
            self.account_num = int(self.data["CustTable"]["AccountNum"])


class InvoiceCustomTableRequest(SuilaInvoiceRequest):
    method = "CreateCustTable"

    @classmethod
    def response_class(cls) -> type[ResponseType]:
        return InvoiceCustomTableResponse  # pragma: no cover


class SuilaInvoiceResponse(InvoiceResponse):

    def __init__(self, request: SuilaInvoiceRequest, xml: str):
        super().__init__(request, xml)
        if self.data is not None:
            self.rec_id = self.data["CustInvoiceTable"]["RecId"]
            self.invoice_id = self.data["CustInvoiceTable"]["InvoiceId"]


class PrismeClient(Prisme):

    mock_recid_counter = 0
    instance = None

    def __init__(
        self,
        wsdl_file: str,
        auth: Dict[str, str],
        proxy: Dict[str, str] | None = None,
        mock=False,
    ):
        super().__init__(wsdl_file, auth, proxy)
        self.mock = mock

    @staticmethod
    def from_settings() -> "PrismeClient":
        prisme_settings: Dict[str, Any] = settings.PRISME  # type: ignore[misc]
        if not PrismeClient.instance:
            if prisme_settings.get("mock", False):
                PrismeClient.instance = PrismeClient("", auth={}, proxy=None, mock=True)
            else:
                PrismeClient.instance = PrismeClient(
                    wsdl_file=prisme_settings["wsdl"],
                    auth=prisme_settings["auth"],
                    proxy=prisme_settings["proxy"],
                    mock=False,
                )
        return PrismeClient.instance

    @staticmethod
    def mock_service(
        request_object: SuilaInvoiceRequest, debug_context: Any = None
    ) -> List[SuilaInvoiceResponse]:  # pragma: no cover
        print("Mock call to Prisme:")
        print(request_object.xml)

        PrismeClient.mock_recid_counter += 1
        return [
            SuilaInvoiceResponse(
                request_object,
                f"""
                <CustInvoiceTable>
                <RecId>{PrismeClient.mock_recid_counter}</RecId>
                <HarborTaxIdFUJ>{request_object.afgift_id}</HarborTaxIdFUJ>
                <InvoiceId>{PrismeClient.mock_recid_counter}</InvoiceId>
                </CustInvoiceTable>
                """,
            )
        ]

    def process_service(
        self, request_object: SuilaInvoiceRequest, debug_context: Any = None
    ) -> List[ResponseType]:
        if self.mock:
            return self.mock_service(request_object, debug_context)
        else:
            return super().process_service(request_object, debug_context)

    def create_request_header(
        self, method: str, area: str = "Suila", client_version: int = 1
    ) -> Any:
        return super().create_request_header(
            method, area, client_version
        )  # pragma: no cover
