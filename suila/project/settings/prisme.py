# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import os

PRISME = {
    # SFTP credentials, etc.
    "host": os.environ["PRISME_HOST"],
    "port": int(os.environ.get("PRISME_PORT") or 22),
    "username": os.environ["PRISME_USER"],
    "password": os.environ["PRISME_PASSWORD"],
    "known_hosts": os.environ.get("PRISME_KNOWN_HOSTS") or None,
    # Configuration for G68/G69 export
    "user_number": int(os.environ.get("PRISME_USER_NUMBER", "0900")),
    "machine_id": int(os.environ["PRISME_MACHINE_ID"]),
    # Folder names
    "g68g69_export_folder": os.environ["PRISME_G68G69_EXPORT_FOLDER"],
    "g68g69_export_mod11_folder": os.environ["PRISME_G68G69_EXPORT_MOD11_FOLDER"],
    "posting_status_folder": os.environ["PRISME_POSTING_STATUS_FOLDER"],
    "b_tax_folder": os.environ["PRISME_B_TAX_FOLDER"],
    "control_folder": os.environ["PRISME_CONTROL_FOLDER"],
}
