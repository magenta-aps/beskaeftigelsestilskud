import json
import sys
from pathlib import Path
from typing import List

from project.util import strtobool
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
VERSION = os.environ.get("VERSION", "1.0.0")
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(os.environ.get("DJANGO_DEBUG", "False")))
HOST_DOMAIN = os.environ.get("HOST_DOMAIN", "http://bf.aka.gl")
ALLOWED_HOSTS: List[str] = json.loads(os.environ.get("ALLOWED_HOSTS", "[]"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

ROOT_URLCONF = "project.urls"

WSGI_APPLICATION = "project.wsgi.application"
