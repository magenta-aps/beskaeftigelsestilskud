# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
from collections import defaultdict
from datetime import date
from typing import List

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.expressions import F
from numpy import std
from tabulate import SEPARATING_LINE, tabulate

from bf.calculate import (
    CalculationEngine,
    InYearExtrapolationEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import (
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    MonthlyIncomeReport,
    Person,
    PersonYear,
)


class Command(BaseCommand):
    engines: List[CalculationEngine] = [
        InYearExtrapolationEngine(),
        TwelveMonthsSummationEngine(),
    ]

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--count", type=int)

    def handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        year = kwargs.get("year") or date.today().year
        person_qs = Person.objects.all()
        if kwargs["count"]:
            person_qs = person_qs[: kwargs["count"]]

        summary_table_by_engine = defaultdict(list)
        for person in person_qs:
            person_year: PersonYear = person.personyear_set.get(year=year)
            qs_a = MonthlyAIncomeReport.objects.alias(
                person=F("person_month__person_year__person"),
                year=F("person_month__person_year__year"),
                month=F("person_month__month"),
            ).filter(person=person.pk)
            qs_b = MonthlyBIncomeReport.objects.alias(
                person=F("person_month__person_year__person"),
                year=F("person_month__person_year__year"),
                month=F("person_month__month"),
            ).filter(person=person.pk)

            self._write_verbose("====================================")
            self._write_verbose(f"CPR: {person.cpr}")
            self._write_verbose("")

            amounts = []
            for month in range(1, 13):
                amounts.append(
                    MonthlyIncomeReport.sum_queryset(
                        qs_a.filter(year=year, month=month)
                    )
                    + MonthlyIncomeReport.sum_queryset(
                        qs_b.filter(year=year, month=month)
                    )
                )
            actual_year_sum = MonthlyIncomeReport.sum_queryset(
                qs_a.filter(year=year)
            ) + MonthlyIncomeReport.sum_queryset(qs_b.filter(year=year))
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
                predictions = []
                for month in range(1, 13):
                    person_month = person_year.personmonth_set.get(month=month)
                    visible_a_reports = qs_a.filter(
                        Q(year__lt=year) | Q(year=year, month__lte=month)
                    )
                    visible_b_reports = qs_b.filter(
                        Q(year__lt=year) | Q(year=year, month__lte=month)
                    )
                    resultat = engine.calculate(
                        visible_a_reports, visible_b_reports, person_month
                    )
                    if resultat is not None:
                        predictions.append(
                            [
                                month,
                                resultat.calculated_year_result,
                                resultat.calculated_year_result - actual_year_sum,
                                (
                                    (
                                        abs(
                                            (
                                                resultat.calculated_year_result
                                                - actual_year_sum
                                            )
                                            / actual_year_sum
                                        )
                                        * 100
                                    )
                                    if actual_year_sum != 0
                                    else 0
                                ),
                            ]
                        )
                        resultat.actual_year_result = actual_year_sum
                        resultat.save()
                self._write_verbose(engine.description)
                self._write_verbose(
                    tabulate(
                        predictions,
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
                        "month_predictions": predictions,
                    }
                )
        for engine, results in summary_table_by_engine.items():
            with open(f"predictions_{engine}.csv", "w") as fp:
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
                            "{:.1f}".format(prediction[3])
                            for prediction in result["month_predictions"]
                        ]
                    )

    def _write_verbose(self, *args):
        if self._verbose:
            self.stdout.write(*args)
