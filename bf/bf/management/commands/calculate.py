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
from bf.models import ASalaryReport, Person


class Command(BaseCommand):
    engines: List[CalculationEngine] = [
        InYearExtrapolationEngine(),
        TwelveMonthsSummationEngine(),
    ]

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)

    def handle(self, *args, **kwargs):
        year = kwargs.get("year") or date.today().year
        summary_table_by_engine = defaultdict(list)
        for person in Person.objects.all():
            qs = ASalaryReport.objects.alias(
                person=F("person_month__person_year__person"),
                year=F("person_month__person_year__year"),
                month=F("person_month__month"),
            ).filter(person=person.pk)
            employers = [x.employer for x in qs.distinct("employer")]
            for employer in employers:
                print("====================================")
                print(f"CPR: {person.cpr}")
                print(f"CVR: {employer.cvr}")
                print("")
                employment = qs.filter(employer=employer)
                amounts = [item.amount for item in employment if item.year == year]
                actual_year_sum = sum(amounts)
                stddev_over_sum = (
                    std(amounts) / actual_year_sum if actual_year_sum != 0 else 0
                )
                print(
                    tabulate(
                        [[item.year, item.month, item.amount] for item in employment]
                        + [SEPARATING_LINE, ["Sum", actual_year_sum]],
                        headers=["År", "Måned", "Beløb"],
                        tablefmt="simple",
                    )
                )
                print("")
                for engine in self.engines:
                    predictions = []
                    for month in range(1, 13):
                        visible_datapoints = employment.filter(
                            Q(year__lt=year) | Q(year=year, month__lte=month)
                        )
                        resultat = engine.calculate(visible_datapoints)
                        if resultat is not None:
                            predictions.append(
                                [
                                    month,
                                    resultat.year_prediction,
                                    resultat.year_prediction - actual_year_sum,
                                    (
                                        (
                                            abs(
                                                (resultat.year_prediction - actual_year_sum)
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
                    print(engine.description)
                    print(
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
                    print("")
                    summary_table_by_engine[engine.__class__.__name__].append(
                        {
                            "cpr": person.cpr,
                            "cvr": employer.cvr,
                            "year_sum": actual_year_sum,
                            "stddev_over_sum": stddev_over_sum,
                            "month_predictions": predictions,
                        }
                    )
        for engine, results in summary_table_by_engine.items():
            with open(f"predictions_{engine}.csv", "w") as fp:
                writer = csv.writer(fp, delimiter=";")
                writer.writerow(
                    ["CPR", "CVR", "Year sum", "Std.Dev / Sum"]
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
                            result["cvr"],
                            result["year_sum"],
                            "{:.3f}".format(result["stddev_over_sum"]),
                        ]
                        + [
                            "{:.1f}".format(prediction[3])
                            for prediction in result["month_predictions"]
                        ]
                    )
