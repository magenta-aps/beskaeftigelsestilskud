# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from django.db import models

from bf.models import ASalaryReport


class CalculationResult(models.Model):
    engine = models.CharField(
        max_length=100,
        choices=(
            # We could create this list with [(cls.__name__, cls.description) for cls in CalculationEngine.__subclasses__()]
            # but that would make a circular import
            ("InYearExtrapolationEngine", "Ekstrapolation af beløb for måneder i indeværende år"),
            ("TwelveMonthsSummationEngine", "Summation af beløb for de seneste 12 måneder"),
        )
    )

    a_salary_report = models.ForeignKey(
        ASalaryReport,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    calculated_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    actual_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
