# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from project.settings.base import TESTING

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_mitid_auth.middleware.LoginManager",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "django_session_timeout.middleware.SessionTimeoutMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]
if not TESTING:
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
