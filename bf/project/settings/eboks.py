# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os

EBOKS = {
    "client_cert": os.environ["EBOKS_CLIENT_CERT"],
    "client_key": os.environ["EBOKS_CLIENT_KEY"],
    "host_verify": os.environ["EBOKS_HOST_VERIFY"],
    "client_id": os.environ["EBOKS_CLIENT_ID"],
    "system_id": os.environ["EBOKS_SYSTEM_ID"],
    "host": os.environ["EBOKS_HOST"],
    "timeout": int(os.environ.get("EBOKS_TIMEOUT") or 60),
}
