# SPDX-FileCopyrightText: 2026 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging

from django.db.models import Q

from suila.management.commands.common import SuilaBaseCommand
from suila.models import FinalSettlement, PersonYear

logger = logging.getLogger(__name__)


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        year = kwargs["year"]
        person_years = (
            PersonYear.objects.filter(
                year_id=year,
                # Require an associated AnnualIncome object
                annual_income_statements__isnull=False,
            )
            .exclude(
                # Exclude those that already have a message
                personmonth__suilaeboksmessage__type="årsopgørelse"
            )
            .exclude(
                person__full_address="",
            )
            .exclude(
                Q(person__full_address="0")
                | Q(person__full_address__contains="9999")
                | Q(person__full_address__contains="Ukendt")
                | Q(person__full_address__contains="Administrativ")
            )
        )
        person_years = person_years.select_related("person")

        def handle_person_year(person_year):
            annual_income = person_year.annual_income_statements.last()
            final_settlement = FinalSettlement(annual_income=annual_income)
            final_settlement.save()
            pdf = final_settlement.pdf
            result = final_settlement.result
            final_settlement.save()
            logger.debug(
                f"Created final settlement {final_settlement.pk} with result"
                + f" {result} and PDF in {pdf}"
            )

        i = 0
        for person_year in person_years:
            handle_person_year(person_year)
            i += 1
        logger.debug(f"Generated {i} final settlements")
