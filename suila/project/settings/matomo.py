# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os
import re

MATOMO = {
    "url": os.environ.get("MATOMO_URL", ""),
    "host": re.sub(r"^https?://", "", os.environ.get("MATOMO_URL", "")),
    "site_id": {
        "suila_public": os.environ.get("MATOMO_SUILA_PUBLIC_SITEID"),
        "suila_private": os.environ.get("MATOMO_SUILA_PRIVATE_SITEID"),
    },
}
