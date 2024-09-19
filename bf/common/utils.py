# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def add_parameters_to_url(url: str, keys_to_add: dict) -> str:
    u = urlparse(url)
    query = parse_qs(u.query, keep_blank_values=True)
    for key, value in keys_to_add.items():
        query[key] = [str(value)]
    u = u._replace(query=urlencode(query, True))
    return urlunparse(u)
