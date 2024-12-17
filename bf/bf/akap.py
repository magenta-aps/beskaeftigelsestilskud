# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

URL_U1A_LIST = "/udbytte/api/u1a"
URL_U1A_ITEMS = "/udbytte/api/u1a/{u1a_id}/items"


class AKAPU1AItem(BaseModel):
    id: int
    u1a_id: int = Field(alias="u1a")
    cpr_cvr_tin: str
    navn: str
    adresse: str
    postnummer: str
    by: str
    land: str
    udbytte: Decimal
    oprettet: datetime

    @property
    def model_dict(self) -> Dict:
        return {
            "u1a_item_id": self.id,
            "u1a_entry_id": None,
            # NOTE: "u1a_entry_id" needs to be populated from the bf-database
            "cpr_cvr_tin": self.cpr_cvr_tin,
            "name": self.navn,
            "address": self.adresse,
            "postal_code": self.postnummer,
            "city": self.by,
            "country": self.land,
            "dividend": self.udbytte,
            "created": self.oprettet,
        }


class AKAPU1A(BaseModel):
    id: int
    navn: str
    revisionsfirma: str
    virksomhedsnavn: str
    cvr: str
    email: str
    regnskabsår: int
    u1_udfyldt: bool = False
    udbytte: Decimal
    noter: Optional[str] = None
    by: str
    dato: date
    underskriftsberettiget: str
    oprettet: datetime
    oprettet_af_cpr: str
    oprettet_af_cvr: Optional[str] = None
    items: Optional[List[AKAPU1AItem]] = None

    @property
    def model_dict(self) -> Dict:
        return {
            "u1a_id": self.id,
            "name": self.navn,
            "accounting_firm": self.revisionsfirma,
            "company_name": self.virksomhedsnavn,
            "cvr": self.cvr,
            "email": self.email,
            "financial_year": self.regnskabsår,
            "u1_filled": self.u1_udfyldt,
            "dividend": self.udbytte,
            "notes": self.noter,
            "city": self.by,
            "date": self.dato,
            "authorized_signatory": self.underskriftsberettiget,
            "created": self.oprettet,
            "created_by_cpr": self.oprettet_af_cpr,
            "created_by_cvr": self.oprettet_af_cvr,
        }


class AKAPAPIPaginatedResponse(BaseModel):
    count: int
    items: List[Dict]


def get_akap_u1a_entries(
    host: str,
    auth_token: str,
    year: Optional[int] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[AKAPU1A]:
    limit = limit if limit else 50
    offset = offset if offset else 0

    query_params = {"limit": limit, "offset": offset}
    if year:
        query_params["regnskabsår"] = year

    resp = requests.get(
        host + URL_U1A_LIST,
        headers={"Authorization": f"Bearer {auth_token}"},
        params=query_params,
    )

    if resp.status_code != 200:
        logger.error(resp.text)
        raise Exception("AKAP udbytte API did not respond with HTTP 200")

    response = AKAPAPIPaginatedResponse.model_validate(resp.json())

    # Recursive call to fetch the next batch of entries
    entries = [AKAPU1A.model_validate(e) for e in response.items]
    if fetch_all and offset + limit < response.count:
        entries += get_akap_u1a_entries(
            host, auth_token, limit=limit, offset=offset + limit
        )

    return entries


def get_akap_u1a_items(
    host: str,
    auth_token: str,
    u1a_id: int,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[AKAPU1AItem]:
    limit = limit if limit else 50
    offset = offset if offset else 0

    resp = requests.get(
        host + URL_U1A_ITEMS.format(u1a_id=u1a_id),
        headers={"Authorization": f"Bearer {auth_token}"},
        params={"limit": limit, "offset": offset},
    )

    if resp.status_code != 200:
        logger.error(resp.text)
        raise Exception("AKAP udbytte API did not respond with HTTP 200")

    response = AKAPAPIPaginatedResponse.model_validate(resp.json())

    # Recursive call to fetch the next batch of entries
    items = [AKAPU1AItem.model_validate(i) for i in response.items]
    if fetch_all and offset + limit < response.count:
        items += get_akap_u1a_items(
            host, auth_token, u1a_id, limit=limit, offset=offset + limit
        )

    return items
