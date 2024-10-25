# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import List

from project.util import strtobool

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
VERSION = os.environ.get("COMMIT_TAG", "")
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(os.environ.get("DJANGO_DEBUG", "False")))
HOST_DOMAIN = os.environ.get("HOST_DOMAIN", "http://bf.aka.gl")
ALLOWED_HOSTS: List[str] = json.loads(os.environ.get("ALLOWED_HOSTS", "[]"))
CSRF_TRUSTED_ORIGINS = [HOST_DOMAIN]

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

ROOT_URLCONF = "project.urls"

WSGI_APPLICATION = "project.wsgi.application"

AUTH_USER_MODEL = "common.User"

# When a calculated benefit differs from last month's benefit by less
# than this amount, reuse prior benefit
CALCULATION_STICKY_THRESHOLD = Decimal("0.05")
CALCULATION_TRIVIAL_LIMIT = Decimal(os.environ.get("CALCULATION_TRIVIAL_LIMIT", "150"))
CALCULATION_QUARANTINE_LIMIT = Decimal(
    os.environ.get("CALCULATION_QUARANTINE_LIMIT", "100")
)

# Payout 80% of what we THINK we should pay out
# The remainder is paid out in December
CALCULATION_SAFETY_FACTOR = Decimal(os.environ.get("CALCULATION_SAFETY_FACTOR", "0.8"))


# If True, allow putting people in quarantine so they get their money in December
# rather than throughout the year
ENFORCE_QUARANTINE = bool(strtobool(os.environ.get("ENFORCE_QUARANTINE", "True")))


class XMLFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        if "Resource 'XMLSchema.xsd' is already loaded" in message:
            return False
        return True


INTERNAL_IPS = [
    "127.0.0.1",
]

TWO_FACTOR_LOGIN_TIMEOUT = 0  # Never timeout
TWO_FACTOR_REMEMBER_COOKIE_AGE = 30 * 24 * 60 * 60  # Re-authenticate once per month
BYPASS_2FA = bool(strtobool(os.environ.get("BYPASS_2FA", "False")))

PITU = {
    "certificate": os.environ.get("PITU_CLIENT_CERT"),
    "private_key": os.environ.get("PITU_CLIENT_CERT_KEY"),
    "root_ca": os.environ.get("PITU_SERVER_CERT"),
    "client_header": os.environ.get("PITU_UXP_CLIENT"),
    "base_url": os.environ.get("PITU_URL"),
    "service": os.environ.get("PITU_SERVICE"),
}
