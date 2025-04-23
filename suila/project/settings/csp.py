# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from project.settings.base import DEBUG, HOST_DOMAIN
from project.settings.matomo import MATOMO

CSP_DEFAULT_SRC = (
    "'self'",
    "localhost:8120" if DEBUG else HOST_DOMAIN,
    MATOMO["host"],
)
CSP_SCRIPT_SRC_ATTR = (
    "'self'",
    "'unsafe-inline'",
    "localhost:8000" if DEBUG else HOST_DOMAIN,
    MATOMO["host"],
)
CSP_STYLE_SRC_ATTR = (
    "'self'",
    "'unsafe-inline'",
)
CSP_STYLE_SRC_ELEM = (
    "'self'",
    "'unsafe-inline'",
    "cdn.jsdelivr.net",
)
CSP_IMG_SRC = (
    "'self'",
    "data:",
    "django-ninja.dev",
)
CSP_FRAME_SRC = (
    "'self'",
    "https://www.youtube.com",
)
