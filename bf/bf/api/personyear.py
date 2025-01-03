# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
from typing import Optional

from django.shortcuts import get_object_or_404
from ninja import Field, ModelSchema
from ninja.filter_schema import FilterSchema
from ninja.params import Query
from ninja_extra import ControllerBase, api_controller, paginate, permissions, route
from ninja_extra.schemas import NinjaPaginationResponseSchema

from bf.api.auth import RestPermission, get_auth_methods
from bf.models import PersonYear


class PersonYearOut(ModelSchema):

    year: int = Field(..., alias="year.year")
    cpr: str = Field(..., alias="person.cpr")

    class Meta:
        model = PersonYear
        fields = [
            "preferred_estimation_engine_a",
            "preferred_estimation_engine_b",
            "tax_scope",
        ]


class PersonYearFilterSchema(FilterSchema):
    cpr: Optional[str] = Field(None, q="person__cpr")
    year: Optional[int] = Field(None, q="year__year")


class PersonYearPermission(RestPermission):
    appname = "bf"
    modelname = "personyear"


@api_controller(
    "/personyear",
    tags=["Person"],
    permissions=[permissions.IsAuthenticated & PersonYearPermission],
)
class PersonYearAPI(ControllerBase):

    @route.get(
        "/{cpr}/{year}",
        response=PersonYearOut,
        auth=get_auth_methods(),
        url_name="personyear_get",
    )
    def get(self, cpr: str, year: int):
        return get_object_or_404(PersonYear, person__cpr=cpr, year__year=year)

    @route.get(
        "",
        response=NinjaPaginationResponseSchema[PersonYearOut],
        auth=get_auth_methods(),
        url_name="personyear_list",
    )
    @paginate()
    def list(self, filters: PersonYearFilterSchema = Query(...)):
        return list(filters.filter(PersonYear.objects.all()))
