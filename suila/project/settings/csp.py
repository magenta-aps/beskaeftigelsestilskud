# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from csp import constants as csp_constants
from project.settings.base import DEBUG, HOST_DOMAIN
from project.settings.matomo import MATOMO

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [
            "'self'",
            "localhost:8120" if DEBUG else HOST_DOMAIN,
            MATOMO["host"],
            # Replaced by 'nonce-<value>' when a view uses `request.csp_nonce`
            csp_constants.NONCE,
        ],
        "script-src-attr": [
            "'self'",
            "'unsafe-inline'",
            "localhost:8000" if DEBUG else HOST_DOMAIN,
            MATOMO["host"],
        ],
        "style-src-attr": [
            "'self'",
            "'unsafe-inline'",
        ],
        "style-src-elem": [
            "'self'",
            "'unsafe-inline'",
            "cdn.jsdelivr.net",
        ],
        "img-src": [
            "'self'",
            "data:",
            "django-ninja.dev",
        ],
        "frame-src": [
            "'self'",
            "https://www.youtube.com",
        ],
    },
}
