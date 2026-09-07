# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
import os
from ast import literal_eval

from project.settings.base import TESTING
from project.settings.upload import MEDIA_ROOT

PRISME = {
    # SFTP credentials, etc.
    "host": os.environ["PRISME_HOST"],
    "port": int(os.environ.get("PRISME_PORT") or 22),
    "username": os.environ["PRISME_USER"],
    "password": os.environ["PRISME_PASSWORD"],
    "known_hosts": json.loads(os.environ.get("PRISME_KNOWN_HOSTS") or "[]"),
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
    "mock": os.environ.get("PRISME_MOCK", False),
    "wsdl": os.environ.get("PRISME_WSDL", ""),
    "auth": {
        "basic": {
            "username": os.environ.get("PRISME_SOAP_USERNAME", ""),
            "domain": os.environ.get("PRISME_SOAP_DOMAIN", ""),
            "password": os.environ.get("PRISME_SOAP_PASSWORD", ""),
        }
    },
    "proxy": {"socks": os.environ.get("PRISME_SOCKS", None)},
    "currency_code": os.environ.get("PRISME_CURRENCY_CODE", "DKK"),
    "department_recid": os.environ.get("PRISME_DEPARTMENT_RECID"),
    "department_recid_ext": os.environ.get("PRISME_DEPARTMENT_RECID_EXT"),
    "invoice_ean": os.environ.get("PRISME_INVOICE_EAN"),
    "order_form_num": os.environ.get("PRISME_ORDER_FORM_NUM"),
    "contact_person_id": os.environ.get("PRISME_CONTACT_PERSON_ID"),
    "project_name": os.environ.get("PRISME_PROJECT_NAME", "Suila"),
    "project_category_id": int(os.environ.get("PRISME_PROJECT_CATEGORY_ID", "1")),
    "finance_law_id": os.environ.get("PRISME_FINANCE_LAW_ID", 0),
    "purpose_id": os.environ.get("PRISME_PURPOSE_ID", 0),
    "type_account_plan_id": os.environ.get("PRISME_TYPE_ACCOUNT_PLAN_ID", 0),
}

# Seconds to wait between retries when talking to Prisme over SFTP. Zero while
# testing, so the tests covering the retry paths do not spend ten real seconds
# each sleeping.
PRISME_RETRY_WAIT_SECONDS = (
    0.0 if TESTING else float(os.environ.get("PRISME_RETRY_WAIT_SECONDS", "1"))
)

# Relative to settings.MEDIA_ROOT
LOCAL_PRISME_CSV_STORAGE = "prisme"

LOCAL_PRISME_CSV_STORAGE_FULL = str(
    os.path.join(
        MEDIA_ROOT,  # type: ignore[misc]
        LOCAL_PRISME_CSV_STORAGE,  # type: ignore[misc]
    )
)
