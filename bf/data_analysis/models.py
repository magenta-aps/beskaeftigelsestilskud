# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from django.db import models
from django.db.models import F, QuerySet

from bf.models import PersonMonth


class CalculationResult(models.Model):

    class Meta:
        unique_together = (("engine", "person_month"),)

    engine = models.CharField(
        max_length=100,
        choices=(
            # We could create this list with [
            #     (cls.__name__, cls.description)
            #     for cls in CalculationEngine.__subclasses__()
            # ]
            # but that would make a circular import
            (
                "InYearExtrapolationEngine",
                "Ekstrapolation af beløb for måneder i indeværende år",
            ),
            (
                "TwelveMonthsSummationEngine",
                "Summation af beløb for de seneste 12 måneder",
            ),
        ),
    )

    person_month = models.ForeignKey(
        PersonMonth, null=True, blank=True, on_delete=models.CASCADE
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

    @property
    def absdiff(self):
        return abs(self.actual_year_result - self.calculated_year_result)

    @property
    def offset(self):
        return (
            (self.absdiff / self.actual_year_result) if self.actual_year_result else 0
        )

    @staticmethod
    def annotate_month(
        qs: QuerySet["CalculationResult"],
    ) -> QuerySet["CalculationResult"]:
        return qs.annotate(f_month=F("person_month__month"))

    @staticmethod
    def annotate_year(
        qs: QuerySet["CalculationResult"],
    ) -> QuerySet["CalculationResult"]:
        return qs.annotate(f_year=F("person_month__person_year__year"))

    @staticmethod
    def annotate_person_year(
        qs: QuerySet["CalculationResult"],
    ) -> QuerySet["CalculationResult"]:
        return qs.annotate(f_person_year=F("person_month__person_year"))
