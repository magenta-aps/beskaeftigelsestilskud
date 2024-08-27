# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import datetime
import re
import time
from decimal import Decimal
from itertools import groupby
from operator import attrgetter
from typing import Iterable, List

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Func, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from bf.data import MonthlyIncomeData
from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    SameAsLastMonthEngine,
    TwelveMonthsSummationEngine,
)
from bf.models import (
    EstimationParameters,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
)


class Command(BaseCommand):
    engines: List[EstimationEngine] = [
        InYearExtrapolationEngine(),
        TwelveMonthsSummationEngine(),
        SameAsLastMonthEngine(),
    ]

    def add_arguments(self, parser):
        parser.add_argument("years", type=str)
        parser.add_argument("--count", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--person", type=int)

    @staticmethod
    def parse_years(years: str) -> Iterable[int]:
        single_match = re.fullmatch(r"^\d{4}$", years)
        if single_match:
            return [single_match.group(0)]
        range_match = re.fullmatch(r"^(\d{4})-(\d{4})$", years)
        if range_match:
            year1 = int(range_match.group(1))
            year2 = int(range_match.group(2))
            return range(min(year1, year2), max(year1, year2) + 1)

    @transaction.atomic
    def handle(self, *args, **kwargs):
        start = time.time()

        years = self.parse_years(kwargs["years"])
        self.verbose = kwargs["verbosity"] > 1
        dry = kwargs["dry"]

        person_qs = Person.objects.all()
        if kwargs["person"]:
            person_qs = person_qs.filter(cpr=kwargs["person"])
        if kwargs["count"]:
            person_qs = person_qs[: kwargs["count"]]

        if not dry:
            self.write_verbose("Removing current `EstimationParameters` objects ...")
            EstimationParameters.objects.filter(
                person__in=person_qs,
            ).delete()

        self.write_verbose("Computing estimation parameters ...")

        person_year_qs = PersonYear.objects.filter(
            person__in=person_qs,
            year__year__in=years,
        )

        data_qs: Iterable[MonthlyIncomeData] = self.get_monthlyincomedata(
            person_year_qs
        )

        for idx, subset in enumerate(self.iterate_by_person(data_qs)):
            self.write_verbose(f"{idx}", ending="\r")
            person_pk = subset[0].person_pk
            person = person_qs.get(pk=person_pk)

            parameter_sets = []
            for engine in self.engines:
                parameters = engine.train(person, subset)
                if parameters is not None:
                    parameter_sets.append(parameters)
        EstimationParameters.objects.bulk_create(parameter_sets)

        duration = datetime.datetime.utcfromtimestamp(time.time() - start)
        self.write_verbose(f"Done (took {duration.strftime('%H:%M:%S')})")

    def get_monthlyincomedata(
        self, person_year_qs: QuerySet[PersonYear]
    ) -> List[MonthlyIncomeData]:

        def sum_amount(incomereport_class):
            return Subquery(
                incomereport_class.objects.filter(
                    month=OuterRef("month"),
                    year=OuterRef("year"),
                    person=OuterRef("person_pk"),
                )
                .annotate(
                    sum_amount=Coalesce(Func("amount", function="Sum"), Decimal(0))
                )
                .values("sum_amount")
            )

        qs = (
            PersonMonth.objects.filter(person_year__in=person_year_qs)
            .values(
                "month",
                person_pk=F("person_year__person__pk"),
                person_month_pk=F("pk"),
                year=F("person_year__year__year"),
            )
            .annotate(
                a_amount=sum_amount(MonthlyAIncomeReport),
                b_amount=sum_amount(MonthlyBIncomeReport),
            )
            .order_by(
                "person_pk",
                "year",
                "month",
            )
        )
        return [MonthlyIncomeData(**value) for value in qs]

    def iterate_by_person(
        self, data_qs: List[MonthlyIncomeData]
    ) -> List[List[MonthlyIncomeData]]:
        # Iterate over `data_qs` and yield a subset of rows for each `person_pk`
        return (
            list(vals) for key, vals in groupby(data_qs, key=attrgetter("person_pk"))
        )

    def write_verbose(self, msg, **kwargs):
        if self.verbose:
            self.stdout.write(msg, **kwargs)
