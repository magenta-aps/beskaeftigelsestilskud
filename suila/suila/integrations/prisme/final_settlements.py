# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import TU, relativedelta
from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr

from suila.integrations.prisme.benefits import BaseExport
from suila.models import FinalSettlement, PrismeBatch, PrismeBatchItem


class FinalSettlementExport(BaseExport):
    def __init__(self, year: int):
        assert year < date.today().year, f"`year` must be less than {date.today().year}"
        self._year = year
        self._month = date.today().month

    def get_queryset(self):
        qs: QuerySet[FinalSettlement] = FinalSettlement.objects.filter(
            annual_income__person_year__year__year=self._year,
            prismebatchitem__isnull=True,
            _result__isnull=False,
            _result__gt=0,
        )

        # Annotate with string version of CPR (zero-padded to 10 digits)
        qs = qs.annotate(
            identifier=LPad(
                Cast("annual_income__person_year__person__cpr", CharField()),
                10,
                Value("0"),
            )
        )
        # Annotate with prefix (first two digits of CPR)
        qs = qs.annotate(prefix=Substr("identifier", 1, 2))
        # Order by prefix and CPR
        qs = qs.order_by("prefix", "annual_income__person_year__person__cpr")
        return qs

    def get_prisme_account_alias_lookup(
        self, obj: FinalSettlement
    ) -> tuple[str | None, int]:
        location_code: str | None = obj.annual_income.person_year.person.location_code
        tax_year: int = self._year
        return location_code, tax_year

    def get_posting_text(self, obj: FinalSettlement) -> str:
        cpr: str = obj.identifier  # type: ignore[attr-defined]
        date_formatted: str = self.get_posting_date(obj).strftime("%b%y").upper()
        return f"SUILA-TAPIT-{cpr}-{date_formatted}"

    def get_transaction_text(self, obj: FinalSettlement) -> str:
        return f"Suila.gl - Årsopgørelse {self._year}"

    def get_payment_amount(self, obj: FinalSettlement) -> Decimal | None:
        return obj._result

    def get_payment_date(self, obj: FinalSettlement) -> date:
        return date(self._year, self._month, 1) + relativedelta(weekday=TU(+3))

    def get_posting_date(self, obj: FinalSettlement) -> date:
        return date(self._year, self._month, 1) + relativedelta(weekday=TU(+2))

    def get_destination_filename(self, prisme_batch: PrismeBatch) -> str:
        return (
            "SUILA_aarsopgoerelse_G68_export_"
            f"{prisme_batch.prefix:02}_{self._year}_{self._month:02}.g68"
        )

    def get_control_list_data(self) -> QuerySet:
        return PrismeBatchItem.objects.none()  # TODO: implement

    def get_control_list_filename(self) -> str:
        return f"SUILA_kontrolliste_aarsopgoerelse_{self._year}_{self._month:02}.csv"

    def _get_prisme_batch_item_instance(
        self,
        prisme_batch: PrismeBatch,
        obj,
        transaction_pair,
        invoice_no,
    ) -> PrismeBatchItem:
        return PrismeBatchItem(
            prisme_batch=prisme_batch,
            final_settlement=obj,
            g68_content=transaction_pair.g68,
            g69_content=transaction_pair.g69,
            invoice_no=invoice_no,
            paused=obj.annual_income.person_year.person.paused,
        )
