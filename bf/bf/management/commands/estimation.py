# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import csv
from collections import defaultdict
from datetime import date
from typing import List

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

    def handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year = kwargs.get("year") or date.today().year
        qs = PersonYear.objects.filter(year__year=year).select_related("person")
        if kwargs["count"]:
            qs = qs[: kwargs["count"]]

        summary_table_by_engine = defaultdict(list)

        results = []
        for person_year in qs:
            person = person_year.person
            qs_a = MonthlyAIncomeReport.objects.all()
            qs_a = MonthlyAIncomeReport.annotate_person(qs_a)
            qs_a = qs_a.filter(f_person=person.pk)
            qs_a = MonthlyAIncomeReport.annotate_year(qs_a)
            qs_a = MonthlyAIncomeReport.annotate_month(qs_a)

            qs_b = MonthlyBIncomeReport.objects.all()
            qs_b = MonthlyBIncomeReport.annotate_person(qs_b)
            qs_b = qs_b.filter(f_person=person.pk)
            qs_b = MonthlyBIncomeReport.annotate_year(qs_b)
            qs_b = MonthlyBIncomeReport.annotate_month(qs_b)

            self._write_verbose("====================================")
            self._write_verbose(f"CPR: {person.cpr}")
            self._write_verbose("")

            amounts = []
            for month in range(1, 13):
                amounts.append(
                    MonthlyIncomeReport.sum_queryset(
                        qs_a.filter(f_year=year, f_month=month)
                    )
                    + MonthlyIncomeReport.sum_queryset(
                        qs_b.filter(f_year=year, f_month=month)
                    )
                )
            actual_year_sum = MonthlyIncomeReport.sum_queryset(
                qs_a.filter(f_year=year)
            ) + MonthlyIncomeReport.sum_queryset(qs_b.filter(f_year=year))
            stddev_over_sum = (
                std(amounts) / actual_year_sum if actual_year_sum != 0 else 0
            )
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
                            if item.f_year < year
                            or (item.f_year == year and item.f_month <= month)
                        ]
                    )
                    visible_b_reports = MonthlyBIncomeReport.objects.filter(
                        id__in=[
                            item.id
                            for item in b_reports
                            if item.f_year < year
                            or (item.f_year == year and item.f_month <= month)
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
                self._write_verbose(engine.description)
                self._write_verbose(
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
                self._write_verbose("")
                summary_table_by_engine[engine.__class__.__name__].append(
                    {
                        "cpr": person.cpr,
                        "year_sum": actual_year_sum,
                        "stddev_over_sum": stddev_over_sum,
                        "month_estimates": estimates,
                    }
                )

                IncomeEstimate.objects.filter(to_delete).delete()
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

    def _write_verbose(self, *args):
        if self._verbose:
            self.stdout.write(*args)
