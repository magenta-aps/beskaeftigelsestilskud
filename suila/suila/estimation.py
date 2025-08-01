# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from itertools import batched, groupby
from math import ceil
from operator import attrgetter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from dateutil.relativedelta import relativedelta
from django.core.management.base import OutputWrapper
from django.db import transaction
from django.db.models import F, QuerySet, Sum
from django.utils import timezone
from project.util import mean_error, root_mean_sq_error, trim_list_first

from suila import data
from suila.data import MonthlyIncomeData
from suila.models import (
    IncomeEstimate,
    IncomeType,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
)


class EstimationEngine:

    description = "Tom superklasse"
    valid_income_types: List[IncomeType] = [
        IncomeType.A,
        IncomeType.U,
    ]

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        raise NotImplementedError

    income_map: Dict[IncomeType, Callable[[MonthlyIncomeData], Decimal]] = {
        IncomeType.A: lambda row: row.a_income,
        IncomeType.U: lambda row: row.u_income,
    }

    @classmethod
    def subset_sum(
        cls,
        relevant: Iterable[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> Decimal:
        return Decimal(0) + sum(
            EstimationEngine.income_map[income_type](row) for row in relevant
        )

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
        person_pk: int | None,
        count: int | None,
        dry_run: bool = True,
        output_stream: Optional[OutputWrapper] = None,
    ):
        now = timezone.now()

        if output_stream is not None:
            output_stream.write("Fetching person_year data ...\n")

        person_year_qs: QuerySet[PersonYear] = PersonYear.objects.filter(
            year__year=year
        ).select_related("person")

        if person_pk:
            person_year_qs = person_year_qs.filter(person=person_pk)
        if count:
            person_year_qs = person_year_qs[:count]

        if output_stream is not None:
            output_stream.write("Fetching person_month_map ...\n")

        person_month_qs = (
            PersonMonth.objects.filter(person_year__person__id=person_pk)
            if person_pk
            else PersonMonth.objects.all()
        )
        person_month_map = {pm.pk: pm for pm in person_month_qs}

        # Create queryset with one row for each `PersonMonth`.
        # Each row contains PKs for person, person month, and values for year and month.
        # Each row also contains summed values for monthly reported A and B income, as
        # each person month can have one or more A or B incomes reported.
        if output_stream is not None:
            output_stream.write("Fetching Person data ...\n")

        person_qs = Person.objects.filter(personyear__in=person_year_qs).values_list(
            "pk", flat=True
        )

        # Process rows in batches
        batch_size = 10  # 10 people, not 10 personmonths
        if output_stream is not None:
            output_stream.write(
                f"Processing batches with a batch-size of: {batch_size} ...\n"
            )

        batches_count = ceil(person_qs.count() / batch_size)

        with transaction.atomic():
            for counter, person_pk_list in enumerate(
                batched(person_qs.iterator(), batch_size), 1
            ):
                batch_results, batch_summaries = EstimationEngine._process_batch(
                    year,
                    person_pk_list,
                    person_month_map,
                    now,
                    dry_run,
                    output_stream,
                )
                if output_stream is not None:
                    output_stream.write(f"Processed batch {counter}/{batches_count}")

    @staticmethod
    def _process_batch(
        year: int,
        person_pk_list: Iterable[int],
        person_month_map: dict[Any, PersonMonth],
        timestamp: datetime,
        dry_run: bool = True,
        output_stream: Optional[OutputWrapper] = None,
    ) -> Tuple[List[IncomeEstimate], List[PersonYearEstimateSummary]]:

        # Det er vigtigt at vi behandler en persons data på én gang,
        # og ikke splitter dem op over flere batches.
        # Det er fordi estimatet skal køre på alle relevante måneder for personen,
        # hvilket er op til 24 måneder tilbage i tid

        # Fjern IncomeEstimate- og PersonYearEstimateSummary for
        # personer i dette batch i dette år
        if not dry_run:
            if output_stream is not None:
                output_stream.write("Removing current `IncomeEstimate` objects ...\n")
            IncomeEstimate.objects.filter(
                person_month__person_year__year_id=year,
                person_month__person_year__person_id__in=person_pk_list,
            ).delete()
            if output_stream is not None:
                output_stream.write(
                    "Removing current `PersonYearEstimateSummary` objects ...\n"
                )
            PersonYearEstimateSummary.objects.filter(
                person_year__year_id=year,
                person_year__person_id__in=person_pk_list,
            ).delete()

        # Fremsøg relevante PersonMonths og annotér dem til estimeringen
        person_month_qs = (
            PersonMonth.objects.filter(
                person_year__year_id__lte=year,
                person_year__year_id__gte=year - 2,
                person_year__person_id__in=person_pk_list,
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
                a_income=Sum("monthlyincomereport__a_income"),
                u_income=Sum("monthlyincomereport__u_income"),
            )
            .order_by(
                "person_pk",
                "_year",
                "month",
            )
        )

        # Frasortér karantæneramte personer og ekskluderede måneder
        # Opbyg en liste af MonthlyIncomeData
        data_qs = [
            data.MonthlyIncomeData(
                month=person_month.month,
                person_pk=person_month.person_pk,  # type: ignore[attr-defined]  # noqa: E501
                person_month_pk=person_month.pk,
                person_year_pk=person_month.person_year_pk,  # type: ignore[attr-defined]  # noqa: E501
                year=person_month.year,
                a_income=Decimal(
                    person_month.a_income or 0  # type: ignore[attr-defined]
                ),
                u_income=Decimal(
                    person_month.u_income or 0  # type: ignore[attr-defined]
                ),
                # b_income=Decimal(person_month.b_income_from_year or 0),
                signal=person_month.signal,
            )
            for person_month in person_month_qs
            if person_month.has_tax_information_period
        ]
        results = []
        summaries = []
        for idx, (key, items) in enumerate(
            groupby(data_qs, key=attrgetter("person_pk"))
        ):
            if output_stream is not None:
                output_stream.write(str(idx), ending="\r")
            group_results, group_summaries = (
                EstimationEngine._process_person_monthly_income_data(
                    year, list(items), person_month_map, timestamp
                )
            )
            results.extend(group_results)
            summaries.extend(group_summaries)

        # Finally commit the DB changes
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

    @staticmethod
    def _process_person_monthly_income_data(
        year: int,
        subset: List[MonthlyIncomeData],
        person_month_map: dict[Any, PersonMonth],
        timestamp: datetime,
    ) -> Tuple[List, List]:
        results = []
        summaries = []

        person_pk = subset[0].person_pk
        first_income_month = EstimationEngine._get_first_income_month(year, subset)
        actual_year_sums = EstimationEngine._get_actual_year_sum(
            year, first_income_month, subset
        )

        # Handle EstimationEngine instances
        person_year = PersonYear.objects.get(person_id=person_pk, year__year=year)
        for engine in EstimationEngine.instances():
            for income_type in engine.valid_income_types:
                engine_results = []
                for month in range(first_income_month, 13):
                    year_month = date(year, month, 1)

                    person_month = None
                    for item in subset:
                        if item.year_month == year_month:
                            # Avoid estimating for months without data,
                            # unless we're estimating B-income
                            if item.signal:
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
                            result.timestamp = timestamp
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
                        resultat.estimated_year_result for resultat in engine_results
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
                    timestamp=timestamp,
                )
                summaries.append(summary)

        return results, summaries

    @staticmethod
    def _get_first_income_month(year: int, subset: List[MonthlyIncomeData]) -> int:
        for month_data in [s for s in subset if s.year == year]:  # pragma: no branch
            if not month_data.amount.is_zero():
                return month_data.month

        return 1

    @staticmethod
    def _get_actual_year_sum(
        year: int, first_income_month: int, subset: List[MonthlyIncomeData]
    ) -> Dict[IncomeType, Dict[int, Decimal]]:
        actual_year_sums: Dict[IncomeType, Dict[int, Decimal]] = {}
        for income_type in IncomeType:
            actual_year_sums[income_type] = {}

            for month in range(first_income_month, 13):
                income_type_sum = Decimal("0.00")

                if income_type == "A":
                    row_income_selector = "a_income"
                elif income_type == "U":
                    row_income_selector = "u_income"
                else:
                    # NOTE: Our old logic defaulted to b_income if it didn't "know"
                    # the income_type, so we continue to do this here
                    row_income_selector = "b_income"

                income_type_sum = sum(
                    getattr(row, row_income_selector)
                    for row in subset
                    if row.year == year and row.year_month <= date(year, month, 1)
                )

                actual_year_sums[income_type][month] = income_type_sum

        return actual_year_sums


"""
Forslag til beregningsmetoder:

* Sum af beløbene for alle måneder i året indtil nu, ekstrapoleret til 12 måneder - DONE
* Sum af beløbene for de seneste 12 måneder - DONE

"""


class InYearExtrapolationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb for måneder i indeværende år"
    valid_income_types: List[IncomeType] = [IncomeType.A]

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        # only handle MonthlyIncomeData for the specified IncomeType
        income_type_filter = InYearExtrapolationEngine.filter_relevant_items(
            income_type
        )
        relevant_items = subset

        # Cut off initial months with no income, and only extrapolate
        # on months after income begins
        relevant_items = cls.relevant(relevant_items, person_month.year_month)

        # Trim off items with no income from the beginning of the list
        relevant_items = trim_list_first(relevant_items, income_type_filter)
        relevant_count = len(relevant_items)
        if relevant_count > 0:
            amount_sum = cls.subset_sum(relevant_items, income_type)

            # Ekstrapolér summen af årets kendte måneder til alle ukendte måneder
            # dvs. "huller" i sekvensen antages at være 0
            # og årets resterende måneder antages at have gennemsnittet af
            # de måneder der har indtægt over 0
            # omitted_count = person_month.month - relevant_count
            # year_estimate = (12 - omitted_count) * amount_sum / relevant_count

            # f.eks. antag at januar og maj er 0,
            # og feb, mar, apr, jun, jul, aug er 10000
            # year_estimate = (12 - 2) * 60000 / 6 = 100000

            # Ekstrapolér summen af årets kendte måneder til resten af året
            # dvs. "huller" i sekvensen antages at være 0
            # og årets resterende måneder antages at have gennemsnittet af
            # alle foregående måneder (inkl. dem der er 0)
            year_estimate = 12 * amount_sum / person_month.month

            # f.eks.:
            # year_estimate = 12 * 60000 / 8 = 90000

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

    @staticmethod
    def filter_relevant_items(income_type):
        def _filter(item):
            if income_type == IncomeType.A:
                return not item.a_income.is_zero()
            return False  # pragma: no cover

        return _filter


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


class MonthlyContinuationEngine(EstimationEngine):
    description = "Ekstrapolation af beløb i indeværende måned, plus foregående beløb"

    @classmethod
    def estimate(
        cls,
        person_month: PersonMonth,
        subset: Sequence[MonthlyIncomeData],
        income_type: IncomeType,
    ) -> IncomeEstimate | None:
        remaining_months = 12 - person_month.month + 1
        sum_this_month = cls.subset_sum(
            cls.relevant_current(subset, person_month.year_month), income_type
        )
        sum_prior_months = cls.subset_sum(
            cls.relevant_prior(subset, person_month.year_month), income_type
        )
        year_estimate = int((remaining_months * sum_this_month) + sum_prior_months)
        return IncomeEstimate(
            estimated_year_result=year_estimate,
            engine=cls.__name__,
            person_month=person_month,
            income_type=income_type,
        )

    @classmethod
    def relevant_prior(
        cls,
        subset: Sequence[MonthlyIncomeData],
        year_month: date,
    ) -> Sequence[MonthlyIncomeData]:
        return list(
            filter(
                lambda item: item.year == year_month.year
                and item.year_month < year_month,
                subset,
            )
        )

    @classmethod
    def relevant_current(
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
