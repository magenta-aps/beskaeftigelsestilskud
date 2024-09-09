# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from bf.models import StandardWorkBenefitCalculationMethod, Year


class Command(BaseCommand):
    def handle(self, *args, **options):
        method, _ = StandardWorkBenefitCalculationMethod.objects.get_or_create(
            id=1,
            defaults={
                "benefit_rate_percent": Decimal("17.5"),
                "personal_allowance": Decimal("58000.00"),
                "standard_allowance": Decimal("10000"),
                "max_benefit": Decimal("15750.00"),
                "scaledown_rate_percent": Decimal("6.3"),
                "scaledown_ceiling": Decimal("250000.00"),
            },
        )
        for year in range(date.today().year - 4, date.today().year + 1):
            Year.objects.update_or_create(
                year=year,
                defaults={
                    "calculation_method": method,
                },
            )
