# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.contrib.auth.models import AbstractUser
from django.core.validators import (
    MaxLengthValidator,
    MinLengthValidator,
    RegexValidator,
)
from django.db import models


class User(AbstractUser):
    cpr = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        validators=[
            MinLengthValidator(10),
            MaxLengthValidator(10),
            RegexValidator(r"\d{10}"),
        ],
    )


class EngineViewPreferences(models.Model):

    user = models.OneToOneField(
        User,
        related_name="engine_view_preferences",
        unique=True,
        default=None,
        null=True,
        on_delete=models.CASCADE,
    )

    show_InYearExtrapolationEngine = models.BooleanField(default=True)
    show_TwelveMonthsSummationEngine = models.BooleanField(default=True)
    show_SameAsLastMonthEngine = models.BooleanField(default=False)
