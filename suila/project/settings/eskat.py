# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os

from project.util import strtobool

ESKAT_BASE_URL = os.environ.get("ESKAT_BASE_URL")
ESKAT_USERNAME = os.environ.get("ESKAT_USERNAME")
ESKAT_PASSWORD = os.environ.get("ESKAT_PASSWORD")
ESKAT_VERIFY = strtobool(os.environ.get("ESKAT_VERIFY", True), True)
