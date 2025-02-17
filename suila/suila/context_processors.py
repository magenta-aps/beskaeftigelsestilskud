# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from django.conf import settings
from django.http import HttpRequest

from suila.models import Person, Year


def date_context(request):
    return {
        "years": sorted(
            list(Year.objects.order_by().values_list("year", flat=True).distinct())
        ),
        "this_year": datetime.datetime.now().year,
        "last_year": datetime.datetime.now().year - 1,
    }


def version_context(request):
    return {"version": settings.VERSION}


def person_context(request):
    if request.user.is_authenticated and request.user.cpr is not None:
        person, _ = Person.objects.get_or_create(
            cpr=request.user.cpr,
            defaults={"name": f"{request.user.first_name} {request.user.last_name}"},
        )
        return {"person": person}
    return {}


def nav_context(request: HttpRequest):
    try:
        return {"current_view": request.resolver_match.view_name}  # type: ignore
    except Exception:
        return {"current_view": None}
