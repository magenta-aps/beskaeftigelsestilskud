from datetime import date
from typing import List

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum
from django.db.models.expressions import F
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
                actual_year_sum = employment.filter(year=year).aggregate(
                    s=Sum("amount")
                )["s"]
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
                                    else None
                                ),
                            ]
                        )
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
