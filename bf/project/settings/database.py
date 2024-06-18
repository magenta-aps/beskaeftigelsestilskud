# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import os

from project.settings.base import ENVIRONMENT, TESTING


def use_mock_db():
    return (ENVIRONMENT == "development") or TESTING


def get_oracle_db_name():
    return (
        f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)"
        f"(HOST={os.environ['ESKAT_HOST']})"
        f"(PORT={os.environ['ESKAT_PORT']}))"
        f"(CONNECT_DATA=(SERVICE_NAME={os.environ['ESKAT_DB']})))"
    )


def get_eskat_database_config():
    if use_mock_db():
        return {
            "ENGINE": "django.db.backends.sqlite3",
        }
    else:
        return {
            "ENGINE": "django.db.backends.oracle",
            "NAME": get_oracle_db_name(),
            "USER": os.environ["ESKAT_USER"],
            "PASSWORD": os.environ["ESKAT_PASSWORD"],
            "HOST": "",
            "PORT": "",
        }


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
    },
    "eskat": get_eskat_database_config(),
}

DATABASE_ROUTERS = ["eskat.database_routers.ESkatRouter"]

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
