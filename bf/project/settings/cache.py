# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

# Cache(s)
# https://docs.djangoproject.com/en/5.0/ref/settings/#std-setting-CACHES

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
    "saml": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "saml_cache",
        "TIMEOUT": 7200,
    },
}
