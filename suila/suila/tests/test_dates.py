# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal

from django.test import TestCase

from suila.dates import get_pause_effect_date, get_payment_date
from suila.models import (
    Person,
    PersonMonth,
    PersonYear,
    PrismeBatch,
    PrismeBatchItem,
    StandardWorkBenefitCalculationMethod,
    Year,
)


class TestPauseEffectDate(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        cls.year = Year.objects.create(year=2024, calculation_method=cls.calc)
        cls.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        cls.person_month1 = PersonMonth.objects.create(
            person_year=cls.person_year, month=1, import_date=date.today()
        )
        cls.person_month2 = PersonMonth.objects.create(
            person_year=cls.person_year, month=2, import_date=date.today()
        )
        cls.person_month3 = PersonMonth.objects.create(
            person_year=cls.person_year, month=3, import_date=date.today()
        )
        cls.person_month4 = PersonMonth.objects.create(
            person_year=cls.person_year, month=4, import_date=date.today()
        )
        cls.person_month8 = PersonMonth.objects.create(
            person_year=cls.person_year, month=8, import_date=date.today()
        )
        cls.person_month12 = PersonMonth.objects.create(
            person_year=cls.person_year, month=12, import_date=date.today()
        )

        cls.prisme_batch = PrismeBatch.objects.create(
            status="sent", export_date=date.today(), prefix=1
        )

        g68_content = (
            "000G6800004011&020900&0300&"
            "07000000000000000000&0800000031700&"
            "09+&1002&1100000101001111&1220250414&"
            "16202504080080400004&"
            "1700000000000027100004&40www.suila.gl takuuk"
        )

        PrismeBatchItem.objects.create(
            person_month=cls.person_month1,
            prisme_batch=cls.prisme_batch,
            g68_content=g68_content,
        )

        PrismeBatchItem.objects.create(
            person_month=cls.person_month2,
            prisme_batch=cls.prisme_batch,
            g68_content=g68_content,
        )
        PrismeBatchItem.objects.create(
            person_month=cls.person_month8,
            prisme_batch=cls.prisme_batch,
            g68_content=g68_content,
        )

        PrismeBatchItem.objects.create(
            person_month=cls.person_month12,
            prisme_batch=cls.prisme_batch,
            g68_content=g68_content,
        )

    def test_get_pause_effect_date(self):

        # Month 1 and 2 were already sent to PRISME,
        # so the pause is effective from month 3
        self.assertEqual(
            get_pause_effect_date(self.person_month1), get_payment_date(2024, 3)
        )

        # Month 2 was already sent to PRISME,
        # so the pause is effective from month 3
        self.assertEqual(
            get_pause_effect_date(self.person_month2), get_payment_date(2024, 3)
        )

        # Month 3 was not sent to PRISME yet,
        # so the pause is effective right away
        self.assertEqual(
            get_pause_effect_date(self.person_month3), get_payment_date(2024, 3)
        )

        # Month 4 was not sent to PRISME yet,
        # so the pause is effective right away
        self.assertEqual(
            get_pause_effect_date(self.person_month4), get_payment_date(2024, 4)
        )

        # Month 8 was already sent to PRISME,
        # so the pause is effective from month 9
        self.assertEqual(
            get_pause_effect_date(self.person_month8), get_payment_date(2024, 9)
        )

        # Month 12 was already sent to PRISME,
        # so the pause is effective from month 1 in the next year
        self.assertEqual(
            get_pause_effect_date(self.person_month12), get_payment_date(2025, 1)
        )
