# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from django.core.management.base import OutputWrapper
from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import Cast, LPad, Substr

from suila.integrations.prisme.benefits import BatchExport
from suila.models import FinalSettlement

# Use account numbers for 2025


class FinalSettlementExport(BatchExport):
    def __init__(self, year: int):
        self._year = year

    def get_final_settlement_queryset(self):
        qs: QuerySet[FinalSettlement] = FinalSettlement.objects.filter(
            annual_income__person_year__year__year=self._year,
            prismebatchitem__isnull=True,
            _result__isnull=False,
        ).exclude(_result=Decimal("0"))

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

    def export_batches(self, stdout: OutputWrapper, verbosity: int):
        pass
