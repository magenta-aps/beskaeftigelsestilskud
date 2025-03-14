# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
import os
import re
from pathlib import Path

import saml2
from django.urls import reverse_lazy
from project.settings.base import DEBUG
from project.util import strtobool

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
AUTHENTICATION_BACKENDS = [
    "django_mitid_auth.saml.backend.Saml2Backend",  # Will log in mitid users
    "django.contrib.auth.backends.ModelBackend",  # Will log in django users
]

DEFAULT_CPR = "1234567890"

SESSION_COOKIE_SECURE = not DEBUG
if not DEBUG:
    SESSION_COOKIE_SAMESITE = "None"
SESSION_EXPIRE_SECONDS = int(os.environ.get("SESSION_EXPIRE_SECONDS") or 1800)
SESSION_EXPIRE_AFTER_LAST_ACTIVITY = True

TWO_FACTOR_LOGIN_TIMEOUT = 0  # Never timeout
TWO_FACTOR_REMEMBER_COOKIE_AGE = 30 * 24 * 60 * 60  # Re-authenticate once per month
BYPASS_2FA = bool(strtobool(os.environ.get("BYPASS_2FA", "False")))
REQUIRE_2FA = bool(strtobool(os.environ.get("REQUIRE_2FA", "True")))

BASE_DIR = Path(__file__).resolve().parent.parent
LOGIN_NAMESPACE = "login:mitid"
LOGIN_TIMEOUT_URL = reverse_lazy("login:login-timeout")
LOGIN_REPEATED_URL = reverse_lazy("login:login-repeat")
LOGIN_NO_CPRCVR_URL = reverse_lazy("login:login-no-cpr")
LOGIN_REDIRECT_URL = reverse_lazy("suila:root")
LOGIN_MITID_REDIRECT_URL = reverse_lazy("login:login")
LOGIN_URL = reverse_lazy("login:login")
LOGOUT_REDIRECT_URL = reverse_lazy("login:logged_out")
LOGIN_PROVIDER_CLASS = os.environ.get("LOGIN_PROVIDER_CLASS") or None
LOGIN_BYPASS_ENABLED = bool(strtobool(os.environ.get("LOGIN_BYPASS_ENABLED", "False")))
LOGIN_WHITELISTED_URLS = [
    "/favicon.ico",
    "/_ht/",
    LOGIN_URL,
    LOGIN_TIMEOUT_URL,
    LOGIN_REPEATED_URL,
    LOGIN_NO_CPRCVR_URL,
    LOGIN_REDIRECT_URL,
    LOGOUT_REDIRECT_URL,
    re.compile("^/api.*"),
]
MITID_TEST_ENABLED = bool(strtobool(os.environ.get("MITID_TEST_ENABLED", "False")))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_EXPIRE_CALLABLE = "login.views.on_session_expired"
SAML_DEFAULT_BINDING = saml2.BINDING_HTTP_REDIRECT
SAML_ATTRIBUTE_MAPPING = {
    "username": "cpr",
    "cpr": "cpr",
    "first_name": "firstname",
    "last_name": "lastname",
    "email": "email",
}


SAML = {
    "enabled": bool(strtobool(os.environ.get("SAML_ENABLED", "False"))),
    "debug": 1,
    "entityid": os.environ.get("SAML_SP_ENTITY_ID"),
    "idp_entity_id": os.environ.get("SAML_IDP_ENTITY_ID"),
    "name": os.environ.get("SAML_SP_NAME") or "Toldbehandling",
    "description": os.environ.get("SAML_SP_DESCRIPTION") or "Beskæftigelsesfradrag",
    "verify_ssl_cert": False,
    "metadata_remote": os.environ.get("SAML_IDP_METADATA"),
    # Til metadata-fetch mellem containere
    "metadata_remote_container": os.environ.get("SAML_IDP_METADATA_CONTAINER"),
    "metadata": {"local": ["/var/cache/suila/idp_metadata.xml"]},  # IdP Metadata
    "service": {
        "sp": {
            "name": os.environ.get("SAML_SP_NAME") or "Beskæftigelsesfradrag",
            "hide_assertion_consumer_service": False,
            "endpoints": {
                "assertion_consumer_service": [
                    (
                        os.environ["SAML_SP_LOGIN_CALLBACK_URI"],
                        saml2.BINDING_HTTP_POST,
                    )
                ],
                "single_logout_service": [
                    (
                        os.environ["SAML_SP_LOGOUT_CALLBACK_URI"],
                        saml2.BINDING_HTTP_REDIRECT,
                    ),
                ],
            },
            "required_attributes": [
                "https://data.gov.dk/model/core/specVersion",
                "https://data.gov.dk/concept/core/nsis/loa",
                "https://data.gov.dk/model/core/eid/cprNumber",
                "https://data.gov.dk/model/core/eid/firstName",
                "https://data.gov.dk/model/core/eid/lastName",
            ],
            "optional_attributes": [
                "https://data.gov.dk/model/core/eid/email",
                "https://data.gov.dk/model/core/eid/professional/orgName",
                "https://data.gov.dk/model/core/eid/professional/cvr",
            ],
            "name_id_format": [
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
            ],
            "signing_algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digest_algorithm": "http://www.w3.org/2000/09/xmldsig#sha1",
            "authn_requests_signed": True,
            "want_assertions_signed": True,
            "want_response_signed": False,
            "allow_unsolicited": True,
            "logout_responses_signed": True,
        }
    },
    "key_file": os.environ.get("SAML_SP_KEY"),
    "cert_file": os.environ.get("SAML_SP_CERTIFICATE"),
    "encryption_keypairs": [
        {
            "key_file": os.environ.get("SAML_SP_KEY"),
            "cert_file": os.environ.get("SAML_SP_CERTIFICATE"),
        },
    ],
    "xmlsec_binary": "/usr/bin/xmlsec1",
    # 'attribute_map_dir': os.path.join(BASE_DIR, 'attribute-maps'),
    "allow_unknown_attributes": True,
    "delete_tmpfiles": True,
    "organization": {
        "name": [("Skattestyrelsen", "da")],
        "display_name": ["Skattestyrelsen"],
        "url": [("https://nanoq.gl", "da")],
    },
    "contact_person": [
        {
            "given_name": os.environ["SAML_CONTACT_TECHNICAL_NAME"],
            "email_address": os.environ["SAML_CONTACT_TECHNICAL_EMAIL"],
            "type": "technical",
        },
        {
            "given_name": os.environ["SAML_CONTACT_SUPPORT_NAME"],
            "email_address": os.environ["SAML_CONTACT_SUPPORT_EMAIL"],
            "type": "support",
        },
    ],
    "preferred_binding": {
        "attribute_consuming_service": [
            "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        ],
        "single_logout_service": [
            "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        ],
    },
}
