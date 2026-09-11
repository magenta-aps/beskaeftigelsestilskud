# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import pandas as pd
from decimal import Decimal
from django.db.models import F, OuterRef, Subquery

ais = AnnualIncome.objects.filter(person_year__year=2025).prefetch_related(
    "final_settlements"
)
fss_latest = FinalSettlement.objects.filter(annual_income=OuterRef("pk")).order_by(
    "-created"
)
fss_first = FinalSettlement.objects.filter(annual_income=OuterRef("pk")).order_by(
    "created"
)
ais_a = ais.annotate(
    latest_result=Subquery(fss_latest.values("_result")[:1]),
    first_result=Subquery(fss_first.values("_result")[:1]),
    cpr=F("person_year__person__cpr"),
)

df = pd.DataFrame(
    list(ais_a.values_list("cpr", "latest_result", "first_result")),
    columns=["CPR", "Result-20/8", "Result-10/9"],
)
df["Difference"] = df["Result-10/9"] - df["Result-20/8"]
df["Difference"] = df["Difference"].mask(df["Difference"] == Decimal("0"))
df = df.dropna()
df.to_csv("/upload/finalsettlement_2025_differences.csv", sep=";", index=False)
