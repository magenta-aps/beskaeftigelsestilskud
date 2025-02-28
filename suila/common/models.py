# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
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
    cert_subject = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default=None,
        unique=True,
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
    show_TwoYearSummationEngine = models.BooleanField(default=True)
    show_MonthlyContinuationEngine = models.BooleanField(default=False)
    show_SelfReportedEngine = models.BooleanField(default=False)


class PageView(models.Model):
    user = models.ForeignKey(
        User,
        related_name="page_views",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    url = models.URLField()
    class_name = models.CharField(max_length=50)
    kwargs = models.JSONField()
    params = models.JSONField()


class ItemView(models.Model):
    pageview = models.ForeignKey(
        PageView,
        on_delete=models.CASCADE,
        related_name="itemviews",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey("content_type", "object_id")
