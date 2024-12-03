# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import os

PRISME = {
    "host": os.environ["PRISME_HOST"],
    "port": int(os.environ.get("PRISME_PORT") or 22),
    "username": os.environ["PRISME_USER"],
    "password": os.environ["PRISME_PASSWORD"],
    "known_hosts": os.environ.get("PRISME_KNOWN_HOSTS") or None,
    "dirs": {
        "production": os.environ["PRISME_PROD_PATH"],
        "development": os.environ["PRISME_TEST_PATH"],
    },
    "destinations": {
        # Our prod server can use both prod and dev on the Prisme server
        "production": ["production", "development"],
        # Our dev server can only use dev on the Prisme server
        "development": ["development"],
        # Our staging server can only use dev on the Prisme server
        "staging": ["development"],
    },
    "user_number": int(os.environ.get("PRISME_USER_NUMBER", "0900")),
    "machine_id": int(os.environ["PRISME_MACHINE_ID"]),
    "posting_status_folder": os.environ["PRISME_POSTING_STATUS_FOLDER"],
}
