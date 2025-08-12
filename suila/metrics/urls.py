# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.urls import path
from metrics.views import (
    health_check_database,
    health_check_eskat,
    health_check_sftp,
    health_check_storage,
)

urlpatterns = [
    path("health/storage", health_check_storage, name="health_check_storage"),
    path("health/database", health_check_database, name="health_check_database"),
    path("health/sftp", health_check_sftp, name="health_check_sftp"),
    path("health/eskat", health_check_eskat, name="health_check_eskat"),
]
