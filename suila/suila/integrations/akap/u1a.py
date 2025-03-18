# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)

URL_U1A_LIST = "/udbytte/api/u1a"
URL_U1A_ITEMS = "/udbytte/api/u1a-items"
URL_U1A_ITEMS_UNIQUE_CPRS = "/udbytte/api/u1a-items/unique/cprs"


class AKAPU1AItem(BaseModel):
    id: int
    u1a: "AKAPU1A"
    cpr_cvr_tin: str
    navn: str
    adresse: str
    postnummer: str
    by: str
    land: str
    udbytte: Decimal
    oprettet: datetime

    def __str__(self):
        return (
            f"{self.navn} - {self.cpr_cvr_tin} - {self.adresse}, "
            f"{self.postnummer} {self.by} - {self.land}"
        )


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
    dato_vedtagelse: date
    underskriftsberettiget: str
    oprettet: datetime
    oprettet_af_cpr: str
    oprettet_af_cvr: Optional[str] = None
    items: Optional[List[AKAPU1AItem]] = None

    def __str__(self):
        return f"{self.navn} - {self.cvr} - {self.email} - {self.regnskabsår}"


class AKAPAPIPaginatedResponse(BaseModel):
    count: int
    items: List[Any]


def get_akap_u1a_entries(
    host: str,
    auth_token: str,
    year: Optional[int] = None,
    cpr: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[AKAPU1A]:
    limit = limit if limit else 50
    offset = offset if offset else 0

    query_params: Dict[str, str | int] = {"limit": limit, "offset": offset}
    if year:
        query_params["regnskabsår"] = year

    if cpr:
        query_params["cpr"] = cpr

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
            host,
            auth_token,
            year=year,
            cpr=cpr,
            limit=limit,
            offset=offset + limit,
            fetch_all=fetch_all,
        )

    return entries


def get_akap_u1a_items(
    host: str,
    auth_token: str,
    u1a_id: Optional[int] = None,
    year: Optional[int] = None,
    cpr: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[AKAPU1AItem]:
    limit = limit if limit else 50
    offset = offset if offset else 0

    query_params: Dict[str, str | int] = {"limit": limit, "offset": offset}
    if u1a_id:
        query_params["u1a"] = u1a_id

    if year:
        query_params["year"] = year

    if cpr:
        query_params["cpr_cvr_tin"] = cpr

    resp = requests.get(
        host + URL_U1A_ITEMS,
        headers={"Authorization": f"Bearer {auth_token}"},
        params=query_params,
    )

    if resp.status_code != 200:
        logger.error(resp.text)
        raise Exception("AKAP udbytte API did not respond with HTTP 200")

    response = AKAPAPIPaginatedResponse.model_validate(resp.json())

    # Recursive call to fetch the next batch of entries
    items = [AKAPU1AItem.model_validate(i) for i in response.items]
    if fetch_all and offset + limit < response.count:
        items += get_akap_u1a_items(
            host,
            auth_token,
            u1a_id=u1a_id,
            year=year,
            cpr=cpr,
            limit=limit,
            offset=offset + limit,
            fetch_all=fetch_all,
        )

    return items


def get_akap_u1a_items_unique_cprs(
    host: str,
    auth_token: str,
    year: Optional[int] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    fetch_all: Optional[bool] = None,
) -> List[str]:
    limit = limit if limit else 50
    offset = offset if offset else 0
    query_params = {"limit": limit, "offset": offset}

    if year:
        query_params["year"] = year

    resp = requests.get(
        host + URL_U1A_ITEMS_UNIQUE_CPRS,
        headers={"Authorization": f"Bearer {auth_token}"},
        params=query_params,
    )

    if resp.status_code != 200:
        logger.error(resp.text)
        raise Exception("AKAP udbytte API did not respond with HTTP 200")

    response = AKAPAPIPaginatedResponse.model_validate(resp.json())

    # Recursive call to fetch the next batch of entries
    cprs = response.items
    if fetch_all and offset + limit < response.count:
        cprs += get_akap_u1a_items_unique_cprs(
            host, auth_token, year, limit, offset + limit, fetch_all=fetch_all
        )

    return cprs
