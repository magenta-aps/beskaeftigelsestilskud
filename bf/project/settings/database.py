# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import os


def get_oracle_db_name():
    return (
        f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)"
        f"(HOST={os.environ['ESKAT_HOST']})"
        f"(PORT={os.environ['ESKAT_PORT']}))"
        f"(CONNECT_DATA=(SERVICE_NAME={os.environ['ESKAT_DB']})))"
    )


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
    },
    "eskat": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": get_oracle_db_name(),
        "USER": os.environ["ESKAT_USER"],
        "PASSWORD": os.environ["ESKAT_PASSWORD"],
        "HOST": "",
        "PORT": "",
    }
}

DATABASE_ROUTERS = ["eskat.database_routers.ESkatRouter"]

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
