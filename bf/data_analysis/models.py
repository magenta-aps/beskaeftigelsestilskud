# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.db import models
from django.db.models import F, QuerySet

from bf.models import PersonMonth, PersonYear


class IncomeEstimate(models.Model):

    class Meta:
        unique_together = (("engine", "person_month"),)

    engine = models.CharField(
        max_length=100,
        choices=(
            # We could create this list with [
            #     (cls.__name__, cls.description)
            #     for cls in EstimationEngine.__subclasses__()
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

    estimated_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )

    actual_year_result = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    @property
    def absdiff(self):
        return abs(self.actual_year_result - self.estimated_year_result)

    @property
    def offset(self):
        return (
            (self.absdiff / self.actual_year_result) if self.actual_year_result else 0
        )

    @staticmethod
    def annotate_month(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_month=F("person_month__month"))

    @staticmethod
    def annotate_year(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_year=F("person_month__person_year__year"))

    @staticmethod
    def annotate_person_year(
        qs: QuerySet["IncomeEstimate"],
    ) -> QuerySet["IncomeEstimate"]:
        return qs.annotate(f_person_year=F("person_month__person_year"))

    def __str__(self):
        return f"{self.engine} ({self.person_month})"


class PersonYearEstimateSummary(models.Model):
    class Meta:
        unique_together = (("person_year", "estimation_engine"),)

    person_year = models.ForeignKey(
        PersonYear,
        on_delete=models.CASCADE,
    )
    estimation_engine = models.CharField(
        max_length=100,
        null=False,
        blank=False,
    )
    offset_percent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
