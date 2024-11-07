# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import groupby
from operator import attrgetter
from typing import Iterable, List, Sequence, Tuple

from dateutil.relativedelta import relativedelta
from django.db.models import F, Func, OuterRef, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce
from project.util import mean_error, root_mean_sq_error, trim_list_first

from bf.data import MonthlyIncomeData
from bf.exceptions import IncomeTypeUnhandledByEngine
from bf.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
)


class EstimationEngine:

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    description = "Tom superklasse"

    @classmethod
    def subset_sum(
        cls,
        relevant: Iterable[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> Decimal:
        # Add Decimal(0) to shut MyPy up
        if income_type == IncomeType.A:
            return Decimal(0) + sum([row.a_amount for row in relevant])
        if income_type == IncomeType.B:  # pragma: no branch
            return Decimal(0) + sum([row.b_amount for row in relevant])

    @classmethod
    def classes(cls) -> List[type[EstimationEngine]]:
        all_subclasses = []
        for subclass in cls.__subclasses__():
            all_subclasses.append(subclass)
            all_subclasses.extend(subclass.classes())
        return all_subclasses

    @staticmethod
    def instances() -> List["EstimationEngine"]:
        return [cls() for cls in EstimationEngine.classes()]

    @classmethod
    def name(cls):
        return cls.__name__

    valid_income_types: List[IncomeType] = [
        IncomeType.A,
        IncomeType.B,
    ]

    @staticmethod
    def valid_engines_for_incometype(income_type: IncomeType):
        return [
            cls
            for cls in EstimationEngine.classes()
            if income_type in cls.valid_income_types
        ]

    @staticmethod
    def estimate_all(
        year: int,
        person: int | None,
        count: int | None,
        dry_run: bool = True,
        output_stream=None,
    ) -> Tuple[List[IncomeEstimate], List[PersonYearEstimateSummary]]:
        person_year_qs: QuerySet[PersonYear] = PersonYear.objects.filter(
            year__year=year
        ).select_related("person")
        if person:
            person_year_qs = person_year_qs.filter(person=person)
        if count:
            person_year_qs = person_year_qs[:count]

        if not dry_run:
            if output_stream is not None:
                output_stream.write("Removing current `IncomeEstimate` objects ...\n")
            IncomeEstimate.objects.filter(
                person_month__person_year__in=person_year_qs
            ).delete()
            if output_stream is not None:
                output_stream.write(
                    "Removing current `PersonYearEstimateSummary` objects ...\n"
                )
            PersonYearEstimateSummary.objects.filter(
                person_year__in=person_year_qs
            ).delete()

        if output_stream is not None:
            output_stream.write("Fetching income data ...\n")

        # Create queryset with one row for each `PersonMonth`.
        # Each row contains PKs for person, person month, and values for year and month.
        # Each row also contains summed values for monthly reported A and B income, as
        # each person month can have one or more A or B incomes reported.

        def sum_amount(incomereport_class):
            return Subquery(
                incomereport_class.objects.filter(
                    month=OuterRef("month"),
                    year=OuterRef("_year"),
                    person=OuterRef("person_pk"),
                )
                .annotate(
                    sum_amount=Coalesce(Func("amount", function="Sum"), Decimal(0))
                )
                .values("sum_amount")
            )

        qs = (
            PersonMonth.objects.filter(
                person_year__person__in=person_year_qs.values("person")
            )
            .select_related("person_year")
            .annotate(
                person_pk=F("person_year__person__pk"),
                person_year_pk=F("person_year__pk"),
                _year=F(  # underscore to avoid collision with class property
                    "person_year__year_id"
                ),
            )
            .annotate(
                a_amount=sum_amount(MonthlyAIncomeReport),
                b_amount=sum_amount(MonthlyBIncomeReport),
            )
            .order_by(
                "person_pk",
                "_year",
                "month",
            )
        )
        data_qs = [
            MonthlyIncomeData(
                month=person_month.month,
                person_pk=person_month.person_pk,
                person_month_pk=person_month.pk,
                person_year_pk=person_month.person_year_pk,
                year=person_month.year,
                a_amount=person_month.a_amount,
                b_amount=person_month.b_amount + person_month.b_income_from_year,
            )
            for person_month in qs
        ]

        person_month_map = {
            pm.pk: pm for pm in PersonMonth.objects.all().select_related("person_year")
        }

        if output_stream is not None:
            output_stream.write("Computing estimates ...\n")
        results = []
        summaries = []

        for idx, (key, items) in enumerate(
            groupby(data_qs, key=attrgetter("person_pk"))
        ):
            subset = list(items)
            if output_stream is not None:
                output_stream.write(str(idx), ending="\r")
            person_pk = subset[0].person_pk

            first_income_month = 1
            for month_data in [  # pragma: no branch
                s for s in subset if s.year == year
            ]:
                if not month_data.amount.is_zero():
                    first_income_month = month_data.month
                    break

            person_year = PersonYear.objects.get(person_id=person_pk, year__year=year)

            actual_year_sums = {
                income_type: {
                    month: sum(
                        row.a_amount if income_type == "A" else row.b_amount
                        for row in subset
                        if row.year == year and row.year_month <= date(year, month, 1)
                    )
                    for month in range(first_income_month, 13)
                }
                for income_type in IncomeType
            }

            for engine in EstimationEngine.instances():
                for income_type in engine.valid_income_types:
                    engine_results = []
                    for month in range(first_income_month, 13):
                        year_month = date(year, month, 1)

                        person_month = None
                        for item in subset:
                            if item.year_month == year_month:
                                person_month = person_month_map[item.person_month_pk]
                                break

                        actual_year_sum = actual_year_sums[income_type][month]

                        if person_month is not None:
                            result: IncomeEstimate | None = engine.estimate(
                                person_month, subset, income_type
                            )
                            if result is not None:
                                result.person_month = person_month
                                result.actual_year_result = actual_year_sum
                                engine_results.append(result)
                                results.append(result)

                    # If we do not have month 12 in the dataset we do not know
                    # what the real income is and can therefore
                    # not evaluate our estimations
                    if (
                        engine_results
                        and actual_year_sum
                        and engine_results[-1].person_month is not None
                        and engine_results[-1].person_month.month == 12
                    ):
                        months_without_income = 12 - len(engine_results)

                        monthly_estimates = [Decimal(0)] * months_without_income + [
                            resultat.estimated_year_result
                            for resultat in engine_results
                        ]

                        me = mean_error(actual_year_sum, monthly_estimates)
                        rmse = root_mean_sq_error(actual_year_sum, monthly_estimates)

                        mean_error_percent = 100 * me / actual_year_sum
                        rmse_percent = 100 * rmse / actual_year_sum
                    else:
                        mean_error_percent = None
                        rmse_percent = None

                    summary = PersonYearEstimateSummary(
                        person_year=person_year,
                        estimation_engine=engine.__class__.__name__,
                        income_type=income_type,
                        mean_error_percent=mean_error_percent,
                        rmse_percent=rmse_percent,
                    )
                    summaries.append(summary)

        if not dry_run:
            if output_stream is not None:
                output_stream.write(
                    f"Writing {len(results)} `IncomeEstimate` objects ...\n"
                )
            IncomeEstimate.objects.bulk_create(results, batch_size=1000)
            if output_stream is not None:
                output_stream.write(
                    f"Writing {len(summaries)} "
                    f"`PersonYearEstimateSummary` objects ...\n"
                )
            PersonYearEstimateSummary.objects.bulk_create(summaries, batch_size=1000)
        return results, summaries


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder - DONE
* Sum af beløbene for de seneste 12 måneder - DONE

"""


class InYearExtrapolationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(subset, person_month.year_month)

        # Trim off items with no income from the beginning of the list
        relevant_items = trim_list_first(
            relevant_items,
            lambda item: not (
                item.a_amount if income_type == IncomeType.A else item.b_amount
            ).is_zero(),
        )

        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(relevant_items, income_type)

            omitted_count = person_month.month - relevant_count
            year_estimate = (12 - omitted_count) * amount_sum / relevant_count
            return IncomeEstimate(
                estimated_year_result=year_estimate,
                engine=cls.__name__,
                income_type=income_type,
            )
        return IncomeEstimate(
            estimated_year_result=Decimal(0),
            engine=cls.__name__,
            income_type=income_type,
        )

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year_month: date
    ) -> Sequence[MonthlyIncomeData]:
        items = [
            item
            for item in subset
            if item.year == year_month.year and item.year_month <= year_month
        ]
        return items


class TwelveMonthsSummationEngine(EstimationEngine):
    description = "Summation af beløb for de seneste 12 måneder"
    # Styrker: Stabile indkomster, indkomster der har samme mønster hert år
    # Svagheder: Outliers (store indkomster i enkelte måneder)
    months = 12

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        months = 12 if person_month.month == 12 else cls.months
        relevant_items = cls.relevant(subset, person_month.year_month, months)
        if len(relevant_items) < months:
            year_estimate = Decimal(0)
        else:
            year_estimate = cls.subset_sum(relevant_items, income_type)
            if months != 12:
                year_estimate *= 12 / Decimal(months)

        return IncomeEstimate(
            estimated_year_result=year_estimate,
            person_month=person_month,
            engine=cls.__name__,
            income_type=income_type,
        )

    @classmethod
    def relevant(
        cls, subset: Sequence[MonthlyIncomeData], year_month: date, months: int
    ) -> Sequence[MonthlyIncomeData]:
        min_year_month = year_month - relativedelta(months=months - 1)
        return list(
            filter(
                lambda item: year_month >= item.year_month >= min_year_month,
                subset,
            )
        )


class TwoYearSummationEngine(TwelveMonthsSummationEngine):
    months = 24
    description = "Summation af beløb for de seneste 24 måneder"


class SameAsLastMonthEngine(EstimationEngine):
    description = "Ekstrapolation af beløb baseret udelukkende på den foregående måned"

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        relevant_items = cls.relevant(subset, person_month.year_month)
        amount_sum = cls.subset_sum(relevant_items, income_type)
        year_estimate = int(12 * amount_sum)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            engine=cls.__name__,
            income_type=income_type,
        )

    @classmethod
    def relevant(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year_month: date,
    ) -> Sequence[MonthlyIncomeData]:
        return list(
            filter(
                lambda item: item.year_month == year_month,
                subset,
            )
        )


class SelfReportedEngine(EstimationEngine):
    description = "Estimering udfra forskudsopgørelsen. Kun B-indkomst."

    valid_income_types: List[IncomeType] = [IncomeType.B]

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        if income_type != IncomeType.B:
            raise IncomeTypeUnhandledByEngine(income_type, cls)
        assessment = person_month.person_year.assessments.order_by("-created").first()
        if assessment is not None:
            if person_month.month == 12:
                estimated_year_result = MonthlyBIncomeReport.objects.filter(
                    year=person_month.year,
                    person=person_month.person,
                ).aggregate(sum=Sum("amount"))["sum"] or Decimal(0)

                # Add any income from final settlement
                estimated_year_result += person_month.person_year.b_income or 0
            else:
                estimated_year_result = (
                    assessment.brutto_b_indkomst
                    - assessment.brutto_b_før_erhvervsvirk_indhandling
                )
        else:
            estimated_year_result = Decimal(0)
        return IncomeEstimate(
            estimated_year_result=estimated_year_result,
            engine=cls.__name__,
            person_month=person_month,
            income_type=income_type,
        )
