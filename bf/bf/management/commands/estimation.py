# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import concurrent
import csv
import time
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple

from data_analysis.models import IncomeEstimate
from django.core.management.base import BaseCommand
from django.db.models import Q
from numpy import std
from tabulate import SEPARATING_LINE, tabulate

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
        parser.add_argument("--threaded", action="store_true")

    def handle(self, *args, **kwargs):
        start = time.time()
        self._verbose = kwargs["verbosity"] > 1
        year = kwargs.get("year") or date.today().year
        threaded = kwargs.get("threaded", False)
        qs = PersonYear.objects.filter(year__year=year).select_related("person")
        if kwargs["count"]:
            qs = qs[: kwargs["count"]]

        summary_table_by_engine = defaultdict(list)

        results = []
        if threaded:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_list = [
                    executor.submit(self.handle_person_year, person_year)
                    for person_year in qs
                ]
                for future in concurrent.futures.as_completed(future_list):
                    thread_results, thread_summary_table_by_engine = future.result()
                    results += thread_results
                    for key, values in thread_summary_table_by_engine.items():
                        summary_table_by_engine[key] += values
        else:
            for person_year in qs:
                thread_results, thread_summary_table_by_engine = (
                    self.handle_person_year(person_year)
                )
                results += thread_results
                for key, values in thread_summary_table_by_engine.items():
                    summary_table_by_engine[key] += values
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

    def _write_verbose(self, *args):
        if self._verbose:
            self.stdout.write(*args)

    def handle_person_year(
        self, person_year: PersonYear
    ) -> Tuple[List[IncomeEstimate], Dict[str, List]]:
        person = person_year.person
        year = person_year.year.year
        results: List[IncomeEstimate] = []
        summary_table_by_engine = defaultdict(list)
        qs_a = MonthlyAIncomeReport.objects.all()
        qs_a = MonthlyAIncomeReport.annotate_person(qs_a)
        qs_a = qs_a.filter(person=person.pk)
        qs_b = MonthlyBIncomeReport.objects.all()
        qs_b = MonthlyBIncomeReport.annotate_person(qs_b)
        qs_b = qs_b.filter(person=person.pk)

        amounts = []
        for month in range(1, 13):
            amounts.append(
                MonthlyIncomeReport.sum_queryset(qs_a.filter(year=year, month=month))
                + MonthlyIncomeReport.sum_queryset(qs_b.filter(year=year, month=month))
            )
        actual_year_sum = MonthlyIncomeReport.sum_queryset(
            qs_a.filter(year=year)
        ) + MonthlyIncomeReport.sum_queryset(qs_b.filter(year=year))
        stddev_over_sum = std(amounts) / actual_year_sum if actual_year_sum != 0 else 0

        output = []
        output.append("====================================")
        output.append(f"CPR: {person.cpr}")
        output.append("")

        self._write_verbose(
            tabulate(
                [[year, month, amounts[month - 1]] for month in range(1, 13)]
                + [SEPARATING_LINE, ["Sum", actual_year_sum]],
                headers=["År", "Måned", "Beløb"],
                tablefmt="simple",
            )
        )

        self._write_verbose("")
        for engine in self.engines:
            estimates = []

            a_reports = list(qs_a)
            b_reports = list(qs_b)

            to_delete = Q()
            for month in range(1, 13):
                person_month = person_year.personmonth_set.get(month=month)
                # We used to filter by year and month directly on qs_a
                # but extracting once and filtering here is ~20%-30% faster
                visible_a_reports = MonthlyAIncomeReport.objects.filter(
                    id__in=[
                        item.id
                        for item in a_reports
                        if item.year < year
                        or (item.year == year and item.month <= month)
                    ]
                )
                visible_b_reports = MonthlyBIncomeReport.objects.filter(
                    id__in=[
                        item.id
                        for item in b_reports
                        if item.year < year
                        or (item.year == year and item.month <= month)
                    ]
                )
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
                    to_delete |= Q(
                        engine=resultat.engine, person_month=resultat.person_month
                    )
            output.append(engine.description)
            output.append(
                tabulate(
                    estimates,
                    headers=[
                        "month",
                        "Forudset årssum",
                        "Difference (beløb)",
                        "Difference (abs.pct)",
                    ],
                    intfmt=("d", "d", "+d", "d"),
                )
            )
            output.append("")
            summary_table_by_engine[engine.__class__.__name__].append(
                {
                    "cpr": person.cpr,
                    "year_sum": actual_year_sum,
                    "stddev_over_sum": stddev_over_sum,
                    "month_estimates": estimates,
                }
            )

            IncomeEstimate.objects.filter(to_delete).delete()
        self._write_verbose("\n".join(output))
        return results, summary_table_by_engine
