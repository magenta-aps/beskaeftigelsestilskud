# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime

from bf.models import Year


def date_context(request):
    return {
        "years": sorted(
            list(Year.objects.order_by().values_list("year", flat=True).distinct())
        ),
        "this_year": datetime.datetime.now().year,
        "last_year": datetime.datetime.now().year - 1,
    }