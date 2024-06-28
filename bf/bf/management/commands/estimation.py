# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import csv
import time
from collections import defaultdict
from datetime import date
from typing import List

from data_analysis.models import IncomeEstimate
from django.core.management.base import BaseCommand

from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import (
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    MonthlyIncomeReport,
    PersonYear,
)


class Command(BaseCommand):
    engines: List[EstimationEngine] = [
        InYearExtrapolationEngine(),
        TwelveMonthsSummationEngine(),
    ]

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--count", type=int)

    def handle(self, *args, **kwargs):
        start = time.time()
        year = kwargs.get("year") or date.today().year
        qs = PersonYear.objects.filter(year__year=year).select_related("person")
        if kwargs["count"]:
            qs = qs[: kwargs["count"]]

        summary_table_by_engine = defaultdict(list)

        IncomeEstimate.objects.filter(person_month__person_year__in=qs).delete()
        results = []
        for person_year in qs:
            person = person_year.person
            qs_a = MonthlyAIncomeReport.objects.filter(person_id=person.pk)
            qs_b = MonthlyBIncomeReport.objects.filter(person_id=person.pk)

            actual_year_sum = MonthlyIncomeReport.sum_queryset(
                qs_a.filter(year=year)
            ) + MonthlyIncomeReport.sum_queryset(qs_b.filter(year=year))

            a_reports = qs_a.values("year", "month", "id")
            b_reports = qs_b.values("year", "month", "id")
            for engine in self.engines:
                estimates = []

                for month in range(1, 13):
                    person_month = person_year.personmonth_set.get(month=month)
                    # We used to filter by year and month directly on qs_a
                    # but extracting once and filtering here is ~20%-30% faster
                    visible_a_reports = MonthlyAIncomeReport.objects.filter(
                        id__in=[
                            item["id"]
                            for item in a_reports
                            if item["year"] < year
                            or (item["year"] == year and item["month"] <= month)
                        ]
                    )
                    visible_b_reports = MonthlyBIncomeReport.objects.filter(
                        id__in=[
                            item["id"]
                            for item in b_reports
                            if item["year"] < year
                            or (item["year"] == year and item["month"] <= month)
                        ]
                    )

                    # visible_a_reports = qs_a.filter(
                    #     Q(year__lt=year) |
                    #     Q(year=year, month__in=range(1, month+1))
                    # )
                    # visible_b_reports = qs_b.filter(
                    #         Q(year__lt=year) |
                    #         Q(year=year, month__in=range(1, month+1))
                    # )

                    resultat: IncomeEstimate = engine.estimate(
                        visible_a_reports, visible_b_reports, person_month
                    )

                    if resultat is not None:
                        resultat.actual_year_result = actual_year_sum
                        estimates.append(
                            [
                                month,
                                resultat.estimated_year_result,
                                resultat.estimated_year_result - actual_year_sum,
                                100 * resultat.offset,
                            ]
                        )
                        results.append(resultat)

        IncomeEstimate.objects.bulk_create(results)
        for engine, results in summary_table_by_engine.items():
            with open(f"estimates_{engine}.csv", "w") as fp:
                writer = csv.writer(fp, delimiter=";")
                writer.writerow(
                    ["CPR", "Year sum", "Std.Dev / Sum"]
                    + [
                        f"{x} % miss"
                        for x in [
                            "Jan",
                            "Feb",
                            "Mar",
                            "Apr",
                            "May",
                            "Jun",
                            "Jul",
                            "Aug",
                            "Sep",
                            "Oct",
                            "Nov",
                            "Dec",
                        ]
                    ]
                )
                for result in results:
                    writer.writerow(
                        [
                            result["cpr"],
                            result["year_sum"],
                            "{:.3f}".format(result["stddev_over_sum"]),
                        ]
                        + [
                            "{:.1f}".format(estimate[3])
                            for estimate in result["month_estimates"]
                        ]
                    )
        print(time.time() - start)
