from datetime import date
from typing import List

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from tabulate import SEPARATING_LINE, tabulate

from bf.calculate import CalculationEngine, InYearExtrapolationEngine, TwelveMonthsSummationEngine
from bf.models import MonthIncome, Person


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
            # person = Person.objects.first()
            qs = MonthIncome.objects.filter(person=person)
            companies = [x.company for x in qs.distinct("company")]
            for company in companies:
                print("====================================")
                print(f"CPR: {person.cpr}")
                print(f"CVR: {company.cvr}")
                print("")
                employment = qs.filter(company=company).order_by("year", "month")
                actual_year_sum = employment.filter(year=year).aggregate(s=Sum("amount"))["s"]
                print(
                    tabulate(
                        list([[item.year, item.month, item.amount] for item in employment])
                        + [SEPARATING_LINE, ["Sum", actual_year_sum]],
                        headers=["År", "Måned", "Beløb"],
                        tablefmt="simple",
                    )
                )
                print("")
                for engine in self.engines:
                    predictions = []
                    for month in range(1, 13):
                        visible_datapoints = employment.filter(Q(year__lt=year)|Q(year=year, month__lte=month))
                        resultat = engine.calculate(visible_datapoints)
                        predictions.append(
                            [
                                month,
                                resultat.year_prediction,
                                resultat.year_prediction - actual_year_sum,
                                (
                                    abs(
                                        (resultat.year_prediction - actual_year_sum)
                                        / actual_year_sum
                                    )
                                    * 100
                                )
                                if actual_year_sum != 0
                                else None,
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
