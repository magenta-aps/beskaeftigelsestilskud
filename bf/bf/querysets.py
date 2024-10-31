# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Self

from django.db.models import F, OuterRef, QuerySet, Subquery, Sum

from bf.models import IncomeEstimate, IncomeType, Person, PersonMonth, PersonYear


class PersonKeyFigureQuerySet(QuerySet):
    @classmethod
    def from_queryset(
        cls,
        queryset: QuerySet[Person],
        year: int,
        month: int,
    ) -> Self:
        qs: PersonKeyFigureQuerySet = cls(
            model=queryset.model,
            query=queryset.query,
            using=queryset.db,
        )
        qs._year = year
        qs._month = month
        return qs._with_key_figures()

    def _with_key_figures(self):
        # Add "private" annotations - used internally by the "public" annotations
        qs = self.annotate(
            _preferred_estimation_engine_a=self._get_preferred_engine_subquery(
                IncomeType.A
            ),
            _preferred_estimation_engine_b=self._get_preferred_engine_subquery(
                IncomeType.B
            ),
            # Needs `_preferred_estimation_engine_a`
            _estimated_year_result_a=self._get_income_estimate_subquery(
                IncomeType.A, "estimated_year_result"
            ),
            # Needs `_preferred_estimation_engine_b`
            _estimated_year_result_b=self._get_income_estimate_subquery(
                IncomeType.B, "estimated_year_result"
            ),
            # Needs `_preferred_estimation_engine_a`
            _actual_year_result_a=self._get_income_estimate_subquery(
                IncomeType.A, "actual_year_result"
            ),
            # Needs `_preferred_estimation_engine_b`
            _actual_year_result_b=self._get_income_estimate_subquery(
                IncomeType.B, "actual_year_result"
            ),
        )
        # Add "public" annotations
        qs = qs.annotate(
            _benefit_paid=self._get_benefit_paid_to_date(),
            # Needs `_estimated_year_result_a` and `_estimated_year_result_b`
            _total_estimated_year_result=self._get_total("estimated_year_result"),
            # Needs `_actual_year_result_a` and `_actual_year_result_b`
            _total_actual_year_result=self._get_total("actual_year_result"),
        )
        return qs

    def _get_benefit_paid_to_date(self) -> Subquery:
        return Subquery(
            PersonMonth.objects.filter(
                person_year__person=OuterRef("pk"),
                person_year__year__year=self._year,
                month__gte=1,
                month__lte=self._month,
            )
            .order_by()
            .values("person_year__person")  # dummy "group by"
            .annotate(sum_benefit_paid=Sum("benefit_paid"))
            .values("sum_benefit_paid")[:1]
        )

    def _get_preferred_engine_subquery(self, income_type: IncomeType) -> Subquery:
        field = f"preferred_estimation_engine_{income_type.value.lower()}"
        return Subquery(
            PersonYear.objects.filter(
                person=OuterRef("pk"),
                year__year=self._year,
            ).values(field)[:1]
        )

    def _get_income_estimate_subquery(
        self,
        income_type: IncomeType,
        field: str,
    ) -> Subquery:
        return Subquery(
            IncomeEstimate.objects.filter(
                person_month__person_year__person=OuterRef("pk"),
                person_month__person_year__year__year=self._year,
                person_month__month=self._month,
                income_type=income_type,
                engine=OuterRef(
                    f"_preferred_estimation_engine_{income_type.value.lower()}"
                ),
            ).values(field)[:1]
        )

    def _get_total(self, field: str) -> F:
        return F(f"_{field}_a") + F(f"_{field}_b")
