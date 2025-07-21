# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_filters",  # pip package: `django-filter`
    "django_tables2",
    "django_bootstrap5",
    "common",
    "suila",
    "login",
    "metrics",
    "django_mitid_auth",
    "data_analysis",
    "data_update",
    "debug_toolbar",
    "django_bootstrap_icons",
    "django_otp",
    "django_otp.plugins.otp_static",
    "django_otp.plugins.otp_totp",
    "django_extensions",
    "two_factor",
    "ninja_extra",
    "mitid_test",
    "simple_history",
    "compressor",
    "crispy_forms",
]
