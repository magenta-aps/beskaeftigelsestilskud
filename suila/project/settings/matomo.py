# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os
import re

MATOMO_URL = os.environ.get("MATOMO_URL", "")
MATOMO_HOST = re.sub(r"^https?://", "", MATOMO_URL)
