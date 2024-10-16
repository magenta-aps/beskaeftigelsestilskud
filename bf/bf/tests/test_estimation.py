# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import sys
from datetime import date
from decimal import Decimal
from io import TextIOBase

from django.test import TestCase

from bf.data import MonthlyIncomeData
from bf.estimation import (
    EstimationEngine,
    InYearExtrapolationEngine,
    SameAsLastMonthEngine,
    SelfReportedEngine,
    TwelveMonthsSummationEngine,
    TwoYearSummationEngine,
)
from bf.exceptions import IncomeTypeUnhandledByEngine
from bf.models import (
    Employer,
    FinalSettlement,
    IncomeEstimate,
    IncomeType,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    PersonYearEstimateSummary,
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
            ending = self.ending if ending is None else ending
            if ending and not msg.endswith(ending):
                msg += ending
            self._out.write(msg)

    @classmethod
    def setUpTestData(cls):
        cls.year = Year.objects.create(year=2024)
        cls.year2 = Year.objects.create(year=2025)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
        )
        cls.person_year2 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year2,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
        )
        cls.employer = Employer.objects.create(
            cvr=12345678,
            name="Kolbøttefabrikken",
        )
        for month, income in enumerate(
            [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000], start=1
        ):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year, month=month, import_date=date.today()
            )
            MonthlyAIncomeReport.objects.create(
                person_month=person_month,
                employer=cls.employer,
                amount=Decimal(income),
            )
        FinalSettlement.objects.create(
            person_year=cls.person_year,
            skattemæssigt_resultat=1200,
        )

        for month, income in enumerate(
            [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000], start=1
        ):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year2, month=month, import_date=date.today()
            )
            MonthlyAIncomeReport.objects.create(
                person_month=person_month,
                employer=cls.employer,
                amount=Decimal(income),
            )

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
                SameAsLastMonthEngine,
            ],
        )
        self.assertEqual(
            EstimationEngine.valid_engines_for_incometype(IncomeType.B),
            [
                InYearExtrapolationEngine,
                TwelveMonthsSummationEngine,
                TwoYearSummationEngine,
                SameAsLastMonthEngine,
                SelfReportedEngine,
            ],
        )

    def test_estimate_all(self):
        output_stream = self.OutputWrapper(sys.stdout, ending="\n")
        EstimationEngine.estimate_all(
            self.year.year,
            self.person_year.pk,
            1,
            False,
            output_stream,
        )

        self.assertEqual(
            list(
                IncomeEstimate.objects.filter(
                    person_month__person_year=self.person_year,
                    engine="InYearExtrapolationEngine",
                    income_type=IncomeType.A,
                )
                .order_by("person_month__month")
                .values_list("person_month__month", "estimated_year_result")
            ),
            [
                (1, Decimal("0.00")),
                (2, Decimal("0.00")),
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

        self.assertEqual(
            list(
                IncomeEstimate.objects.filter(
                    person_month__person_year=self.person_year,
                    engine="TwelveMonthsSummationEngine",
                    income_type=IncomeType.A,
                ).values_list("person_month__month", "estimated_year_result")
            ),
            [
                (1, Decimal("0.00")),
                (2, Decimal("0.00")),
                (3, Decimal("0.00")),
                (4, Decimal("0.00")),
                (5, Decimal("0.00")),
                (6, Decimal("0.00")),
                (7, Decimal("0.00")),
                (8, Decimal("0.00")),
                (9, Decimal("0.00")),
                (10, Decimal("0.00")),
                (11, Decimal("0.00")),
                (12, Decimal("10000.00")),
            ],
        )

        summary = PersonYearEstimateSummary.objects.get(
            person_year=self.person_year,
            estimation_engine="TwelveMonthsSummationEngine",
            income_type=IncomeType.A,
        )
        self.assertEqual(summary.mean_error_percent, Decimal("-91.67"))
        self.assertEqual(summary.rmse_percent, Decimal("95.74"))

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
                (1, Decimal("0.00")),
                (2, Decimal("0.00")),
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

    def test_b_income_from_year(self):
        for month in PersonMonth.objects.filter(person_year=self.person_year):
            self.assertEqual(month.b_income_from_year, 100)


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
            preferred_estimation_engine_b="InYearExtrapolationEngine",
        )
        cls.employer = Employer.objects.create(
            cvr=12345678,
            name="Kolbøttefabrikken",
        )
        cls.months = []
        cls.reports = []
        for month, income in enumerate(
            [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000], start=1
        ):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year, month=month, import_date=date.today()
            )
            cls.months.append(person_month)
            cls.reports.append(
                MonthlyAIncomeReport.objects.create(
                    person_month=person_month,
                    employer=cls.employer,
                    amount=Decimal(income),
                )
            )

    def test_name(self):
        self.assertEqual(InYearExtrapolationEngine.name(), "InYearExtrapolationEngine")

    def test_estimate(self):
        data = [
            MonthlyIncomeData(
                month=report.person_month.month,
                year=report.person_month.year,
                a_amount=report.amount,
                person_pk=self.person.pk,
                person_year_pk=self.person_year.pk,
                person_month_pk=report.person_month.pk,
                b_amount=Decimal(0),
            )
            for report in self.reports
        ]
        for month, expectation in enumerate(
            [
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("9750.00"),
                Decimal("10000.00"),
                Decimal("9666.67"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year, month=month
            )
            income_estimate = InYearExtrapolationEngine.estimate(
                person_month,
                data,
                IncomeType.A,
            )
            self.assertEqual(
                income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                expectation,
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
            preferred_estimation_engine_b="TwelveMonthsSummationEngine",
        )
        cls.person_year1 = PersonYear.objects.create(
            person=cls.person,
            year=cls.year1,
            preferred_estimation_engine_a="TwelveMonthsSummationEngine",
            preferred_estimation_engine_b="TwelveMonthsSummationEngine",
        )
        cls.employer = Employer.objects.create(
            cvr=12345678,
            name="Kolbøttefabrikken",
        )
        cls.months = []
        cls.reports = []
        for year in (cls.person_year0, cls.person_year1):
            for month, income in enumerate(
                [0, 0, 1000, 1000, 1000, 900, 1100, 800, 1200, 1000, 1000, 1000],
                start=1,
            ):
                person_month = PersonMonth.objects.create(
                    person_year=year, month=month, import_date=date.today()
                )
                cls.months.append(person_month)
                cls.reports.append(
                    MonthlyAIncomeReport.objects.create(
                        person_month=person_month,
                        employer=cls.employer,
                        amount=Decimal(income),
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
                a_amount=report.amount,
                person_pk=self.person.pk,
                person_year_pk=report.person_month.person_year.pk,
                person_month_pk=report.person_month.pk,
                b_amount=Decimal(0),
            )
            for report in self.reports
        ]

        for month, expectation in enumerate(
            [
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("10000.00"),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year0, month=month
            )
            income_estimate = TwelveMonthsSummationEngine.estimate(
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
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("10000.00"),
            ],
            start=1,
        ):
            person_month = PersonMonth.objects.get(
                person_year=self.person_year1, month=month
            )
            income_estimate = TwelveMonthsSummationEngine.estimate(
                person_month,
                data,
                IncomeType.A,
            )
            self.assertEqual(
                income_estimate.estimated_year_result.quantize(Decimal("0.01")),
                expectation,
                month,
            )


class TestSelfReportedEngine(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.year = Year.objects.create(year=2024)
        cls.person = Person.objects.create(
            name="Jens Hansen",
            cpr="1234567890",
        )
        cls.employer = Employer.objects.create(
            cvr=12345678,
            name="Kolbøttefabrikken",
        )
        cls.person_year = PersonYear.objects.create(
            person=cls.person,
            year=cls.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="SelfReportedEngine",
        )

        cls.person_months = []
        for month in range(1, 13):
            person_month = PersonMonth.objects.create(
                person_year=cls.person_year, month=month, import_date=date.today()
            )
            cls.person_months.append(person_month)
            MonthlyBIncomeReport.objects.create(
                person_month=person_month,
                trader=cls.employer,
                amount=Decimal(10000),
            )
        cls.assessment = PersonYearAssessment.objects.create(
            person_year=cls.person_year,
            renteindtægter=Decimal(0),
            uddannelsesstøtte=Decimal(0),
            honorarer=Decimal(0),
            underholdsbidrag=Decimal(0),
            andre_b=Decimal(0),
            brutto_b_før_erhvervsvirk_indhandling=Decimal(0),
            erhvervsindtægter_sum=Decimal(50000),
            e2_indhandling=Decimal(20000),
            brutto_b_indkomst=Decimal(70000),
        )

    def test_name(self):
        self.assertEqual(SelfReportedEngine.name(), "SelfReportedEngine")

    def test_cannot_calculate_a(self):
        for person_month in self.person_months:
            with self.assertRaises(IncomeTypeUnhandledByEngine):
                SelfReportedEngine.estimate(person_month, [], IncomeType.A)

    def test_calculate_b(self):
        for person_month in self.person_months:
            income_estimate = SelfReportedEngine.estimate(
                person_month, [], IncomeType.B
            )
            self.assertIsNotNone(income_estimate)
            self.assertEqual(income_estimate.engine, "SelfReportedEngine")
            self.assertEqual(income_estimate.income_type, IncomeType.B)
            self.assertEqual(income_estimate.person_month, person_month)
            self.assertEqual(
                income_estimate.estimated_year_result,
                Decimal(70000) if person_month.month < 12 else Decimal(120000),
            )
