from typing import List

from django.core.management.base import BaseCommand
from django.db.models import Sum
from tabulate import SEPARATING_LINE, tabulate

from bf.calculate import CalculationEngine, InYearExtrapolationEngine
from bf.models import MonthIncome, Person


class Command(BaseCommand):
    engines: List[CalculationEngine] = [
        InYearExtrapolationEngine(),
    ]

    def handle(self, *args, **kwargs):
        for person in Person.objects.all():
            # person = Person.objects.first()
            qs = MonthIncome.objects.filter(person=person)
            companies = [x.company for x in qs.distinct("company")]
            for company in companies:
                print("====================================")
                print(f"CPR: {person.cpr}")
                print(f"CVR: {company.cvr}")
                print("")
                employment = qs.filter(company=company).order_by("month")
                actual_year_sum = employment.aggregate(s=Sum("amount"))["s"]
                print(
                    tabulate(
                        list([[item.month, item.amount] for item in employment])
                        + [SEPARATING_LINE, ["Sum", actual_year_sum]],
                        headers=["Måned", "Beløb"],
                        tablefmt="simple",
                    )
                )
                print("")
                forudsigelser = []
                for month in range(1, 13):
                    for engine in self.engines:
                        resultat = engine.calculate(employment.filter(month__lte=month))
                        forudsigelser.append(
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
                        forudsigelser,
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
