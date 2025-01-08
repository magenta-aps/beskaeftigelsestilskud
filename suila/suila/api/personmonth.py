# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
from decimal import Decimal
from typing import Optional

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from ninja import Field, ModelSchema
from ninja.filter_schema import FilterSchema
from ninja.params import Query
from ninja_extra import ControllerBase, api_controller, paginate, permissions, route
from ninja_extra.schemas import NinjaPaginationResponseSchema

from suila.api.auth import RestPermission, get_auth_methods
from suila.models import PersonMonth


class PersonMonthOut(ModelSchema):

    cpr: str = Field(..., alias="person_year.person.cpr")
    year: int = Field(..., alias="person_year.year.year")
    income: Decimal = Field(..., alias="amount_sum")
    a_income: Optional[Decimal] = None
    b_income: Optional[Decimal] = None
    b_income_from_year: Decimal = Field(..., alias="b_income_from_year")

    class Meta:
        model = PersonMonth
        fields = [
            "month",
            "municipality_code",
            "municipality_name",
            "fully_tax_liable",
            "estimated_year_result",
            "estimated_year_benefit",
            "actual_year_benefit",
            "prior_benefit_paid",
            "benefit_paid",
        ]

    @staticmethod
    def resolve_a_income(obj) -> Decimal | None:
        return obj.monthlyincomereport_set.aggregate(Sum("a_income"))["a_income__sum"]

    @staticmethod
    def resolve_b_income(obj) -> Decimal | None:
        return obj.monthlyincomereport_set.aggregate(Sum("b_income"))["b_income__sum"]


class PersonMonthFilterSchema(FilterSchema):
    cpr: Optional[str] = Field(
        None, q="person_year__person__cpr"
    )  # type: ignore[call-overload]
    year: Optional[int] = Field(
        None, q="person_year__year__year"
    )  # type: ignore[call-overload]
    month: Optional[int] = Field(None, q="month")  # type: ignore[call-overload]


class PersonMonthPermission(RestPermission):
    appname = "bf"
    modelname = "personmonth"


@api_controller(
    "/personmonth",
    tags=["PersonMonth"],
    permissions=[permissions.IsAuthenticated & PersonMonthPermission],
)
class PersonMonthAPI(ControllerBase):

    @route.get(
        "/{cpr}/{year}/{month}",
        response=PersonMonthOut,
        auth=get_auth_methods(),
        url_name="personmonth_get",
    )
    def get(self, cpr: str, year: int, month: int):
        return get_object_or_404(
            PersonMonth,
            person_year__person__cpr=cpr,
            person_year__year__year=year,
            month=month,
        )

    @route.get(
        "",
        response=NinjaPaginationResponseSchema[PersonMonthOut],
        auth=get_auth_methods(),
        url_name="personmonth_list",
    )
    @paginate()
    def list(self, filters: PersonMonthFilterSchema = Query(...)):
        return list(
            filters.filter(
                PersonMonth.objects.all().order_by(
                    "person_year__person__cpr", "person_year__year", "month"
                )
            )
        )
