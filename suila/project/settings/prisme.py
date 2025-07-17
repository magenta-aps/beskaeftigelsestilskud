# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import os
from ast import literal_eval

from project.settings.upload import MEDIA_ROOT

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
    # List of CPRs that are output to their *own* file in the "mod11" folder, rather
    # than the file shared by all other non-mod11 CPRs.
    "mod11_separate_cprs": literal_eval(
        os.environ.get("PRISME_MOD11_SEPARATE_CPRS", "[]")
    ),
}

# Relative to settings.MEDIA_ROOT
LOCAL_PRISME_CSV_STORAGE = "prisme"

LOCAL_PRISME_CSV_STORAGE_FULL = str(
    os.path.join(
        MEDIA_ROOT,  # type: ignore[misc]
        LOCAL_PRISME_CSV_STORAGE,  # type: ignore[misc]
    )
)
