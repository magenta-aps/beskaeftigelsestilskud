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

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

ROOT_URLCONF = "project.urls"

WSGI_APPLICATION = "project.wsgi.application"

AUTH_USER_MODEL = "common.User"

# When a calculated benefit differs from last month's benefit by less
# than this amount, reuse prior benefit
CALCULATION_STICKY_THRESHOLD = Decimal("0.05")


class XMLFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        if "Resource 'XMLSchema.xsd' is already loaded" in message:
            return False
        return True


INTERNAL_IPS = [
    "127.0.0.1",
]
