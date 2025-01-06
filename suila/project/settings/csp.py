# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from project.settings.base import DEBUG, HOST_DOMAIN

CSP_DEFAULT_SRC = (
    "'self'",
    "localhost:8000" if DEBUG else HOST_DOMAIN,
)
CSP_SCRIPT_SRC_ATTR = (
    "'self'",
    "localhost:8000" if DEBUG else HOST_DOMAIN,
)
CSP_STYLE_SRC_ATTR = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC_ELEM = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", "data:")
