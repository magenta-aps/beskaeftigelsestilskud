# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock, patch

from common.utils import get_people_in_quarantine
from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import get_current_timezone

from suila.data import MonthlyIncomeData
from suila.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    MonthlyContinuationEngine,
    TwelveMonthsSummationEngine,
    TwoYearSummationEngine,
)
from suila.models import (
    IncomeEstimate,
    IncomeType,
    ManagementCommands,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    PersonYearEstimateSummary,
    StandardWorkBenefitCalculationMethod,
    TaxInformationPeriod,
    Year,
)


class TestEstimationEngine(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.calculation_method = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        cls.year = Year.objects.create(
            year=2024, calculation_method=cls.calculation_method
        )
        cls.year2 = Year.objects.create(
            year=2025, calculation_method=cls.calculation_method
        )
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        cls.person_year2 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year2,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        # Create tax information periods covering the entire tax years for person year
        # 1 and 2.
        cls.period1 = TaxInformationPeriod.objects.create(
            person_year=cls.person_year,
            tax_scope="FULL",
            start_date=cls.get_datetime(cls.person_year.year.year, 1, 1),
            end_date=cls.get_datetime(cls.person_year.year.year, 12, 31),
        )
        cls.period2 = TaxInformationPeriod.objects.create(
            person_year=cls.person_year2,
            tax_scope="FULL",
            start_date=cls.get_datetime(cls.person_year2.year.year, 1, 1),
            end_date=cls.get_datetime(cls.person_year2.year.year, 12, 31),
        )

        for month, income in enumerate(
            [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000], start=1
        ):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year, month=month, import_date=date.today()
            )
            MonthlyIncomeReport.objects.create(
                person_month=person_month,
                salary_income=Decimal(income),
            )
        PersonYearAssessment.objects.create(
            person_year=cls.person_year,
            valid_from=datetime(
                cls.person_year.year_id, 1, 1, 0, 0, 0, tzinfo=get_current_timezone()
            ),
            catch_sale_factory_income=1200,
        )

        for month, income in enumerate(
            # Udelader december med vilje
            [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000],
            start=1,
        ):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year2, month=month, import_date=date.today()
            )
            MonthlyIncomeReport.objects.create(
                person_month=person_month,
                salary_income=Decimal(income),
            )

    @classmethod
    def get_datetime(cls, year: int, month: int, day: int) -> datetime:
        return datetime(year, month, day, tzinfo=get_current_timezone())

    def setUp(self):
        IncomeEstimate.objects.all().delete()

    def test_estimate(self):
        month = self.person_year.personmonth_set.first()
        with self.assertRaises(NotImplementedError):
            EstimationEngine.estimate(
                month,
                month.incomeestimate_set.all(),
                IncomeType.A,
            )

    def test_valid_engines_for_incometype(self):
        self.assertEqual(
            EstimationEngine.valid_engines_for_incometype(IncomeType.A),
            [
                InYearExtrapolationEngine,
                TwelveMonthsSummationEngine,
                TwoYearSummationEngine,
                MonthlyContinuationEngine,
            ],
        )

    def estimate_all(
        self, year, person_pk, count, dry_run=False, stdout=None, *args, **kwargs
    ):
        cpr = Person.objects.get(pk=person_pk).cpr if person_pk else None
        call_command(
            ManagementCommands.ESTIMATE_INCOME,
            year=year,
            count=count,
            cpr=cpr,
            stdout=stdout or StringIO(),
            dry=dry_run,
            **kwargs,
        )

    def test_estimate_all(self):
        self.estimate_all(
            self.year.year,
            self.person.pk,
            1,
            False,
        )

        income_estimates = list(
            IncomeEstimate.objects.filter(
                person_month__person_year=self.person_year,
                engine="InYearExtrapolationEngine",
                income_type=IncomeType.A,
            )
            .order_by("person_month__month")
            .values_list("person_month__month", "estimated_year_result")
        )
        self.assertEqual(
            income_estimates,
            [
                (3, Decimal("4000.00")),
                (4, Decimal("6000.00")),
                (5, Decimal("7200.00")),
                (6, Decimal("7800.00")),
                (7, Decimal("8571.43")),
                (8, Decimal("8700.00")),
                (9, Decimal("9333.33")),
                (10, Decimal("9600.00")),
                (11, Decimal("9818.18")),
                (12, Decimal("10000.00")),
            ],
        )
        income_estimates = list(
            IncomeEstimate.objects.filter(
                person_month__person_year=self.person_year,
                engine="TwelveMonthsSummationEngine",
                income_type=IncomeType.A,
            ).values_list("person_month__month", "estimated_year_result")
        )
        self.assertEqual(
            income_estimates,
            [
                (3, Decimal("1000.00")),
                (4, Decimal("2000.00")),
                (5, Decimal("3000.00")),
                (6, Decimal("3900.00")),
                (7, Decimal("5000.00")),
                (8, Decimal("5800.00")),
                (9, Decimal("7000.00")),
                (10, Decimal("8000.00")),
                (11, Decimal("9000.00")),
                (12, Decimal("10000.00")),
            ],
        )

        summary = PersonYearEstimateSummary.objects.get(
            person_year=self.person_year,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.A,
        )
        self.assertEqual(summary.mean_error_percent, Decimal("-54.42"))
        self.assertEqual(summary.rmse_percent, Decimal("63.76"))

        self.estimate_all(
            self.year2.year,
            self.person.pk,
            1,
            False,
        )

        self.assertEqual(
            list(
                IncomeEstimate.objects.filter(
                    person_month__person_year=self.person_year2,
                    engine="InYearExtrapolationEngine",
                    income_type=IncomeType.A,
                )
                .order_by("person_month__month")
                .values_list("person_month__month", "estimated_year_result")
            ),
            [
                (3, Decimal("4000.00")),
                (4, Decimal("6000.00")),
                (5, Decimal("7200.00")),
                (6, Decimal("7800.00")),
                (7, Decimal("8571.43")),
                (8, Decimal("8700.00")),
                (9, Decimal("9333.33")),
                (10, Decimal("9600.00")),
                (11, Decimal("9818.18")),
            ],
        )

        summary = PersonYearEstimateSummary.objects.get(
            person_year=self.person_year2,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.A,
        )
        self.assertIsNone(summary.mean_error_percent)
        self.assertIsNone(summary.rmse_percent)

    def test_estimate_all_not_taxable(self):
        # Arrange: remove tax information period
        self.period1.delete()
        # Act
        self.estimate_all(
            self.year.year,
            self.person.pk,
            1,
            False,
        )
        # Assert
        income_estimates = IncomeEstimate.objects.filter(
            person_month__person_year=self.person_year,
            engine="InYearExtrapolationEngine",
            income_type=IncomeType.A,
        ).count()
        self.assertEqual(income_estimates, 0)

    def test_estimate_all_None_inputs(self):
        self.estimate_all(self.year.year, None, None, False)
        # When person=None and count = None the PersonYear queryset contains
        # all personYears
        all_person_years = PersonYear.objects.filter(year=self.year.year)
        result_person_years = [
            estimate.person_month.person_year
            for estimate in IncomeEstimate.objects.all()
        ]
        for person_year in all_person_years:
            self.assertIn(person_year, result_person_years)

    def test_estimate_all_dry_run(self):

        IncomeEstimate.objects.create(
            person_month=PersonMonth.objects.filter(
                person_year=self.person_year
            ).first(),
            estimated_year_result=12341122,
            income_type=IncomeType.A,
            engine="InYearExtrapolationEngine",
        )

        self.estimate_all(self.year.year, None, None, dry_run=True)

        self.assertEqual(
            IncomeEstimate.objects.filter(estimated_year_result=12341122).count(), 1
        )

        self.estimate_all(self.year.year, None, None, dry_run=False)

        # One person * 10 months * 4 engines * 2 incometypes
        # NOTE: InYearExtrapolationEngine only handles A-IncomeType
        self.assertEqual(IncomeEstimate.objects.all().count(), 70)

        self.assertEqual(
            IncomeEstimate.objects.filter(estimated_year_result=12341122).count(), 0
        )

    @mock.patch("suila.estimation.EstimationEngine.instances")
    def test_estimate_all_invalid_estimate(self, instances):

        MockEngine = MagicMock()
        MockEngine.estimate.return_value = None
        MockEngine.valid_income_types = [IncomeType.A]

        instances.return_value = [MockEngine]

        self.estimate_all(self.year.year, None, None)
        instances.assert_called()

    def test_quarantined(self):
        # Indstil månedsindkomster, så:
        # sum < 500000 (øvre grænse), og
        # sum + stddev > 500000
        for month, month_income in enumerate(
            [
                30000,
                30000,
                41250,
                41250,
                41250,
                41250,
                41250,
                41250,
                41250,
                41250,
                52500,
                52500,
            ],
            1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year, month=month
            )
            person_month.monthlyincomereport_set.all().delete()
            MonthlyIncomeReport.objects.create(
                person_month=person_month,
                salary_income=Decimal(month_income),
            )
        quarantine_df = get_people_in_quarantine(self.year2.year, {self.person.cpr})
        self.assertTrue(quarantine_df.loc[self.person.cpr, "earns_too_much"])
        self.assertTrue(quarantine_df.loc[self.person.cpr, "in_quarantine"])

    def test_verbose(self):
        stdout = StringIO()
        self.estimate_all(
            self.year.year, self.person.pk, 1, False, stdout=stdout, verbosity=3
        )

        self.assertIn("Done", stdout.getvalue())

    @patch("suila.management.commands.estimate_income.EstimationEngine")
    def test_estimate_all_years(self, estimation_engine_mock):
        self.estimate_all(
            None,
            self.person.pk,
            1,
            False,
        )

        years = Year.objects.all()
        calls = estimation_engine_mock.estimate_all.call_args_list

        self.assertGreater(len(years), 1)
        for i, year in enumerate(years):
            self.assertEqual(calls[i][0][0], year.year)


class TestInYearExtrapolationEngine(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year = Year.objects.create(year=2024)

        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        cls.months = []
        cls.reports = []

        # Create A-income test-data
        for month, incomes in enumerate(
            [
                (0, 0, 0),
                (0, 0, 0),
                (1000, 0, 45000),
                (1000, 0, 0),
                (1000, 0, 0),
                (900, 0, 0),
                (1100, 0, 0),
                (800, 0, 0),
                (1200, 0, 0),
                (1000, 0, 0),
                (1000, 0, 0),
                (1000, 0, 0),
            ],
            start=1,
        ):
            a_income, b_income, u_income = incomes

            # Create the month
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year, month=month, import_date=date.today()
            )
            cls.months.append(person_month)

            # Create A-income
            if a_income > 0:
                cls.reports.append(
                    MonthlyIncomeReport.objects.create(
                        person_month=person_month,
                        salary_income=Decimal(a_income),
                    )
                )

            # Create U-income
            if u_income > 0:
                cls.reports.append(
                    MonthlyIncomeReport.objects.create(
                        person_month=person_month,
                        u_income=Decimal(u_income),
                    )
                )

    def test_name(self):
        self.assertEqual(InYearExtrapolationEngine.name(), "InYearExtrapolationEngine")

    def test_estimate(self):
        data = [
            MonthlyIncomeData(
                month=report.person_month.month,
                year=report.person_month.year,
                a_income=report.a_income,
                b_income=Decimal(0),
                u_income=report.u_income,
                person_pk=self.person.pk,
                person_year_pk=self.person_year.pk,
                person_month_pk=report.person_month.pk,
                signal=True,
            )
            for report in self.reports
        ]

        for month, expectations in enumerate(
            [
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("4000.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("6000.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("7200.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("7800.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("8571.43"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("8700.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("9333.33"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("9600.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("9818.18"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("0.00")),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year, month=month
            )

            for idx, expected_income in enumerate(expectations):
                income_type = None
                match idx:
                    case 0:
                        income_type = IncomeType.A
                    case 1:
                        income_type = IncomeType.B
                    case 2:
                        income_type = IncomeType.U

                if not income_type:
                    raise Exception(f"unknown expected-income-index: {idx}")

                income_estimate = InYearExtrapolationEngine.estimate(
                    person_month, data, income_type
                )

                self.assertEqual(
                    income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                    expected_income,
                    month,
                )


class TwelveMonthsSummationEngineTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year0 = Year.objects.create(year=2023)
        cls.year1 = Year.objects.create(year=2024)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year0 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year0,
            preferred_estimation_engine_a="TwelveMonthsSummationEngine",
        )
        cls.person_year1 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year1,
            preferred_estimation_engine_a="TwelveMonthsSummationEngine",
        )

        cls.months = []
        cls.reports = []
        for year in (cls.person_year0, cls.person_year1):
            for month, incomes in enumerate(
                [
                    (0, 0),
                    (0, 0),
                    (1000, 45000),
                    (1000, 0),
                    (1000, 0),
                    (900, 0),
                    (1100, 0),
                    (800, 0),
                    (1200, 0),
                    (1000, 0),
                    (1000, 0),
                    (1000, 0),
                ],
                start=1,
            ):
                a_income, u_income = incomes

                person_month = PersonMonth.objects.create(
                    person_year=year, month=month, import_date=date.today()
                )
                cls.months.append(person_month)

                # Create MonthlyIncomeReport for all incomes
                cls.reports.append(
                    MonthlyIncomeReport.objects.create(
                        person_month=person_month,
                        salary_income=Decimal(a_income),
                        u_income=Decimal(u_income),
                    )
                )

    def test_name(self):
        self.assertEqual(
            TwelveMonthsSummationEngine.name(), "TwelveMonthsSummationEngine"
        )

    def test_estimate(self):
        data = [
            MonthlyIncomeData(
                month=report.person_month.month,
                year=report.person_month.year,
                a_income=report.a_income,
                u_income=report.u_income,
                person_pk=self.person.pk,
                person_year_pk=report.person_month.person_year.pk,
                person_month_pk=report.person_month.pk,
                signal=True,
            )
            for report in self.reports
        ]

        # Assert year-0
        for month, expectations in enumerate(
            [
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00")),
                (Decimal("1000.00"), Decimal("45000.00")),
                (Decimal("2000.00"), Decimal("45000.00")),
                (Decimal("3000.00"), Decimal("45000.00")),
                (Decimal("3900.00"), Decimal("45000.00")),
                (Decimal("5000.00"), Decimal("45000.00")),
                (Decimal("5800.00"), Decimal("45000.00")),
                (Decimal("7000.00"), Decimal("45000.00")),
                (Decimal("8000.00"), Decimal("45000.00")),
                (Decimal("9000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year0, month=month
            )

            for idx, expected_income in enumerate(expectations):
                income_type = None
                match idx:
                    case 0:
                        income_type = IncomeType.A
                    case 1:
                        income_type = IncomeType.U

                if not income_type:
                    raise Exception(f"unknown expected-income-index: {idx}")

                income_estimate = TwelveMonthsSummationEngine.estimate(
                    person_month,
                    data,
                    income_type,
                )

                self.assertEqual(
                    income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                    expected_income,
                    month,
                )

        # Assert year-1
        for month, expectations in enumerate(
            [
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("45000.00")),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year1, month=month
            )

            for idx, expected_income in enumerate(expectations):
                income_type = None
                match idx:
                    case 0:
                        income_type = IncomeType.A
                    case 1:
                        income_type = IncomeType.U

                if not income_type:
                    raise Exception(f"unknown expected-income-index: {idx}")

                income_estimate = TwelveMonthsSummationEngine.estimate(
                    person_month,
                    data,
                    income_type,
                )

                self.assertEqual(
                    income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                    expected_income,
                    month,
                )


class TwoYearSummationEngineTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year0 = Year.objects.create(year=2023)
        cls.year1 = Year.objects.create(year=2024)
        cls.year2 = Year.objects.create(year=2025)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year0 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year0,
            preferred_estimation_engine_a="TwoYearSummationEngine",
        )
        cls.person_year1 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year1,
            preferred_estimation_engine_a="TwoYearSummationEngine",
        )
        cls.person_year2 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year2,
            preferred_estimation_engine_a="TwoYearSummationEngine",
        )
        cls.months = []
        cls.reports = []
        for year, months in (
            (
                cls.person_year0,
                [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000],
            ),
            (
                cls.person_year1,
                [1200, 1000, 900, 800, 1000, 1100, 1300, 1200, 1100, 1200, 1000, 900],
            ),
            (
                cls.person_year2,
                [1300, 1100, 800, 900, 1100, 1200, 1000, 1100, 1000, 1200, 1100, 1300],
            ),
        ):
            for month, income in enumerate(months, start=1):
                person_month = PersonMonth.objects.create(
                    person_year=year, month=month, import_date=date.today()
                )
                cls.months.append(person_month)
                cls.reports.append(
                    MonthlyIncomeReport.objects.create(
                        person_month=person_month,
                        salary_income=Decimal(income),
                    )
                )

    def test_name(self):
        self.assertEqual(TwoYearSummationEngine.name(), "TwoYearSummationEngine")

    def test_estimate(self):
        data = [
            MonthlyIncomeData(
                month=report.person_month.month,
                year=report.person_month.year,
                a_income=report.a_income,
                b_income=Decimal(0),
                u_income=Decimal(0),
                person_pk=self.person.pk,
                person_year_pk=report.person_month.person_year.pk,
                person_month_pk=report.person_month.pk,
                signal=True,
            )
            for report in self.reports
        ]

        for month, expectation in enumerate(
            [
                Decimal("5600.00"),
                Decimal("6100.00"),
                Decimal("6550.00"),
                Decimal("6950.00"),
                Decimal("7450.00"),
                Decimal("8000.00"),
                Decimal("8650.00"),
                Decimal("9250.00"),
                Decimal("9800.00"),
                Decimal("10400.00"),
                Decimal("10900.00"),
                Decimal("12700.00"),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year1, month=month
            )
            income_estimate = TwoYearSummationEngine.estimate(
                person_month,
                data,
                IncomeType.A,
            )
            self.assertEqual(
                income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                expectation,
                month,
            )

        for month, expectation in enumerate(
            [
                Decimal("12000.00"),
                Decimal("12550.00"),
                Decimal("12450.00"),
                Decimal("12400.00"),
                Decimal("12450.00"),
                Decimal("12600.00"),
                Decimal("12550.00"),
                Decimal("12700.00"),
                Decimal("12600.00"),
                Decimal("12700.00"),
                Decimal("12750.00"),
                Decimal("13100.00"),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year2, month=month
            )
            income_estimate = TwoYearSummationEngine.estimate(
                person_month,
                data,
                IncomeType.A,
            )
            self.assertEqual(
                income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                expectation,
                month,
            )
