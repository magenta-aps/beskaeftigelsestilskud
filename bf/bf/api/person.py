# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"

from typing import Optional

from django.shortcuts import get_object_or_404
from ninja import Field, FilterSchema, ModelSchema, Query
from ninja_extra import ControllerBase, api_controller, permissions, route
from ninja_extra.pagination import paginate
from ninja_extra.schemas import NinjaPaginationResponseSchema

from bf.api.auth import RestPermission, get_auth_methods
from bf.models import Person


class PersonOut(ModelSchema):
    class Meta:
        model = Person
        fields = [
            "cpr",
            "name",
            "address_line_1",
            "address_line_2",
            "address_line_3",
            "address_line_4",
            "address_line_5",
            "full_address",
            "civil_state",
            "location_code",
        ]


class PersonFilterSchema(FilterSchema):
    cpr: Optional[str] = None
    name: Optional[str] = Field(None, q="name__iexact")
    name_contains: Optional[str] = Field(None, q="name__icontains")
    address_contains: Optional[str] = Field(None, q="full_address__icontains")
    location_code: Optional[str] = None


class PersonPermission(RestPermission):
    appname = "bf"
    modelname = "person"


@api_controller(
    "/person",
    tags=["Person"],
    permissions=[permissions.IsAuthenticated & PersonPermission],
)
class PersonAPI(ControllerBase):

    @route.get(
        "/{cpr}",
        response=PersonOut,
        auth=get_auth_methods(),
        url_name="person_get",
    )
    def get(self, cpr: str):
        return get_object_or_404(Person, cpr=cpr)

    @route.get(
        "",
        response=NinjaPaginationResponseSchema[PersonOut],
        auth=get_auth_methods(),
        url_name="person_list",
    )
    @paginate()
    def list(self, filters: PersonFilterSchema = Query(...)):
        return list(filters.filter(Person.objects.all()).order_by("cpr"))
