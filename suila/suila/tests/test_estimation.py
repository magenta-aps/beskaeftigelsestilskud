# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from io import TextIOBase
from unittest import mock
from unittest.mock import MagicMock, call

from common.utils import get_people_in_quarantine
from django.test import TestCase
from django.utils.timezone import get_current_timezone
from pandas import DataFrame

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
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    PersonYearEstimateSummary,
    StandardWorkBenefitCalculationMethod,
    Year,
)


class TestEstimationEngine(TestCase):

    class OutputWrapper(TextIOBase):

        def __init__(self, out, ending="\n"):
            self._out = out
            self.ending = ending

        def __getattr__(self, name):
            return getattr(self._out, name)

        def flush(self):
            if hasattr(self._out, "flush"):
                self._out.flush()

        def isatty(self):
            return hasattr(self._out, "isatty") and self._out.isatty()

        def write(self, msg="", style_func=None, ending=None):
            pass

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

    def test_estimate_all(self):
        output_stream = self.OutputWrapper(sys.stdout, ending="\n")
        EstimationEngine.estimate_all(
            self.year.year,
            self.person.pk,
            1,
            False,
            output_stream,
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
                (3, Decimal("10000.00")),
                (4, Decimal("10000.00")),
                (5, Decimal("10000.00")),
                (6, Decimal("9750.00")),
                (7, Decimal("10000.00")),
                (8, Decimal("9666.67")),
                (9, Decimal("10000.00")),
                (10, Decimal("10000.00")),
                (11, Decimal("10000.00")),
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

        EstimationEngine.estimate_all(
            self.year2.year,
            self.person.pk,
            1,
            False,
            output_stream,
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
                (3, Decimal("10000.00")),
                (4, Decimal("10000.00")),
                (5, Decimal("10000.00")),
                (6, Decimal("9750.00")),
                (7, Decimal("10000.00")),
                (8, Decimal("9666.67")),
                (9, Decimal("10000.00")),
                (10, Decimal("10000.00")),
                (11, Decimal("10000.00")),
            ],
        )

        summary = PersonYearEstimateSummary.objects.get(
            person_year=self.person_year2,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.A,
        )
        self.assertIsNone(summary.mean_error_percent)
        self.assertIsNone(summary.rmse_percent)

    def test_estimate_all_None_inputs(self):
        EstimationEngine.estimate_all(self.year.year, None, None, False)
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

        EstimationEngine.estimate_all(self.year.year, None, None, dry_run=True)

        self.assertEqual(
            IncomeEstimate.objects.filter(estimated_year_result=12341122).count(), 1
        )

        EstimationEngine.estimate_all(self.year.year, None, None, dry_run=False)

        self.assertEqual(IncomeEstimate.objects.all().count(), 40)
        self.assertEqual(
            IncomeEstimate.objects.filter(estimated_year_result=12341122).count(), 0
        )

    @mock.patch("suila.estimation.EstimationEngine.instances")
    def test_estimate_all_invalid_estimate(self, instances):

        MockEngine = MagicMock()
        MockEngine.estimate.return_value = None
        MockEngine.valid_income_types = [IncomeType.A]

        instances.return_value = [MockEngine]

        EstimationEngine.estimate_all(self.year.year, None, None)
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

    @mock.patch("django.utils.timezone.now")
    @mock.patch("common.utils.get_people_in_quarantine")
    @mock.patch("suila.data.MonthlyIncomeData", autospec=True)
    def test_quarantined_estimate(
        self,
        monthlyincomedata: MagicMock,
        get_people_in_quarantine: MagicMock,
        now: MagicMock,
    ):
        get_people_in_quarantine.return_value = DataFrame(
            {
                "in_quarantine": [True],
                "quarantine_reason": ["Earns too much"],
                "earns_too_little": [False],
                "earns_too_much": [True],
            },
            index=[self.person.cpr],
        )
        now.return_value = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(TypeError):
            # Mocking breaker noget i metoden, men det sker efter
            # vi har fået det vi skal bruge i assertions nedenfor
            EstimationEngine.estimate_all(
                self.year.year, self.person.pk, count=1, dry_run=True
            )

        # Asserts
        get_people_in_quarantine.assert_called()
        monthlyincomedata.assert_called()
        exclude_months = {(2024, 12), (2025, 1)}
        for month in range(1, 13):
            try:
                person_month = PersonMonth.objects.get(
                    person_year__year=self.year.year, month=month
                )
            except PersonMonth.DoesNotExist:
                continue

            data = {
                "year": self.year.year,
                "month": month,
                "person_pk": self.person.pk,
                "person_month_pk": person_month.pk,
                "person_year_pk": person_month.person_year.pk,
                "a_income": sum(
                    person_month.monthlyincomereport_set.all().values_list(
                        "a_income", flat=True
                    )
                ),
                "u_income": Decimal(person_month.u_income_from_year or 0),
            }

            if (self.year.year, month) in exclude_months:
                self.assertNotIn(
                    call(**data),
                    monthlyincomedata.call_args_list,
                    f"year: {self.year.year}, month: {month}",
                )
            else:
                self.assertIn(
                    call(**data),
                    monthlyincomedata.call_args_list,
                    f"year: {self.year.year}, month: {month}",
                )


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

        # Create A-income test-data
        cls.months = []
        cls.reports = []
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

            # TODO: Create B-income

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
            )
            for report in self.reports
        ]

        for month, expectations in enumerate(
            [
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("450000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("405000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("360000.00")),
                (Decimal("9750.00"), Decimal("0.00"), Decimal("315000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("270000.00")),
                (Decimal("9666.67"), Decimal("0.00"), Decimal("225000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("180000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("135000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("90000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
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

                person_month = PersonMonth.objects.create(
                    person_year=year, month=month, import_date=date.today()
                )
                cls.months.append(person_month)

                # Create MonthlyIncomeReport for all incomes
                cls.reports.append(
                    MonthlyIncomeReport.objects.create(
                        person_month=person_month,
                        salary_income=Decimal(a_income),
                        b_income=Decimal(b_income),
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
                b_income=report.b_income,
                u_income=report.u_income,
                person_pk=self.person.pk,
                person_year_pk=report.person_month.person_year.pk,
                person_month_pk=report.person_month.pk,
            )
            for report in self.reports
        ]

        # Assert year-0
        for month, expectations in enumerate(
            [
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
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
                        income_type = IncomeType.B
                    case 2:
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
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
                (Decimal("10000.00"), Decimal("0.00"), Decimal("45000.00")),
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
                        income_type = IncomeType.B
                    case 2:
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
