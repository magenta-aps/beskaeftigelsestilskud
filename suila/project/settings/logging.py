# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import os

from project.settings.base import ENVIRONMENT, TESTING

LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "suppress_xml": {
            "()": "project.settings.base.XMLFilter",
        },
    },
    "formatters": {
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "gunicorn": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["suppress_xml"],
        },
    },
    "root": {
        "handlers": ["gunicorn"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["gunicorn"],
            "level": "INFO",
            "propagate": False,
        },
        "weasyprint": {
            "handlers": ["gunicorn"],
            "level": "ERROR",
            "propagate": False,
        },
        "fontTools": {
            "handlers": ["gunicorn"],
            "level": "ERROR",
            "propagate": False,
        },
        "paramiko": {
            "handlers": ["gunicorn"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

log_filename = "/suila.log"
if os.path.isfile(log_filename) and ENVIRONMENT != "development":
    LOGGING["handlers"]["file"] = {
        "class": "logging.FileHandler",  # eller WatchedFileHandler
        "filename": log_filename,
        "formatter": "simple",
    }
    LOGGING["root"] = {
        "handlers": ["gunicorn", "file"],
        "level": "INFO",
    }
    LOGGING["loggers"]["django"]["handlers"].append("file")

if TESTING:
    LOGGING["handlers"]["gunicorn"]["class"] = "logging.NullHandler"
