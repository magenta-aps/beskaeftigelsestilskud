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


class AKAPAPIPaginatedResponse(BaseModel):
    count: int
    items: List[Dict]


def get_akap_u1a_entries(
    host: str,
    auth_token: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[AKAPU1A]:
    limit = limit if limit else 50
    offset = offset if offset else 0

    resp = requests.get(
        host + URL_U1A_LIST,
        headers={"Authorization": f"Bearer {auth_token}"},
        params={"limit": limit, "offset": offset},
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
