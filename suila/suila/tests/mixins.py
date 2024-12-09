# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from suila.models import (
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    StandardWorkBenefitCalculationMethod,
    Year,
)


class BaseEnvMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person = Person.objects.create(name="Person", cpr="1234567890")
        cls.employer = Employer.objects.create(name="Employer", cvr=12345678)
        cls.calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        cls.year = Year.objects.create(year=2020, calculation_method=cls.calc)
        cls.personyear = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
        )

    def get_or_create_person_month(self, month: int, **kwargs) -> PersonMonth:
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=self.personyear,
            month=month,
            defaults=kwargs,
        )
        return person_month

    def get_or_create_monthly_income_report(
        self,
        person_month: PersonMonth,
        **kwargs,
    ) -> MonthlyIncomeReport:
        monthly_income_report, _ = MonthlyIncomeReport.objects.create(
            employer=self.employer,
            person=self.person,
            person_month=person_month,
            month=person_month.month,
            year=person_month.person_year.year,
            defaults=kwargs,
        )
        return monthly_income_report
