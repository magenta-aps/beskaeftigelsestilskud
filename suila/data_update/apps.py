# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.apps import AppConfig


class DataUpdateConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "data_update"
