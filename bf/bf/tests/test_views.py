# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Sum
from django.test import TestCase
from django.test.client import RequestFactory
from django.test.testcases import SimpleTestCase
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import ContextMixin, View

from bf.models import (
    Employer,
    IncomeEstimate,
    IncomeType,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)
from bf.views import (
    CategoryChoiceFilter,
    PersonDetailBenefitView,
    PersonDetailIncomeView,
    PersonDetailView,
    PersonSearchView,
    YearMonthMixin,
)


class PersonEnv(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Add persons
        cls.person1, _ = Person.objects.update_or_create(cpr=1, location_code=1)
        cls.person2, _ = Person.objects.update_or_create(cpr=2, location_code=1)
        cls.person3, _ = Person.objects.update_or_create(cpr=3, location_code=None)
        # Add data to person 1
        year, _ = Year.objects.update_or_create(year=2020)
        person_year, _ = PersonYear.objects.update_or_create(
            person=cls.person1,
            year=year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
        )
        # 12 PersonMonth objects where each month amount is equal to the month number
        person_months = [
            PersonMonth(
                person_year=person_year,
                month=i,
                benefit_paid=i,
                import_date=date(2020, 1, 1),
            )
            for i in range(1, 13)
        ]
        PersonMonth.objects.bulk_create(person_months)
        # 2 * 2 * 12 MonthlyIncomeReport objects
        employer1, _ = Employer.objects.update_or_create(name="Employer 1", cvr=1)
        employer2, _ = Employer.objects.update_or_create(name="Employer 2", cvr=2)
        for employer in (employer1, employer2):
            for field in ("salary_income", "disability_pension_income"):
                income_reports = []
                for person_month in person_months:
                    income_report = MonthlyIncomeReport(
                        person_month=person_month,
                        # employer=employer,
                        **{field: person_month.benefit_paid * 10},
                    )
                    income_report.update_amount()
                    income_reports.append(income_report)
                MonthlyIncomeReport.objects.bulk_create(income_reports)
        # 2 * 12 IncomeEstimate objects
        for income_type in IncomeType:
            income_estimates = [
                IncomeEstimate(
                    person_month=person_month,
                    income_type=income_type,
                    engine="InYearExtrapolationEngine",
                    estimated_year_result=(idx + 1) * 100,
                    actual_year_result=(idx + 1) * 150,
                )
                for idx, person_month in enumerate(person_months)
            ]
            IncomeEstimate.objects.bulk_create(income_estimates)


class TestCategoryChoiceFilter(PersonEnv):
    def setUp(self):
        super().setUp()
        self.instance = CategoryChoiceFilter(
            field_name="location_code",
            field=Person.location_code,
        )

    def test_choices(self):
        self.assertListEqual(
            # self.instance.extra["choices"] is a callable
            self.instance.extra["choices"](),
            [
                # 2 persons have location code "1"
                ("1", "1 (2)"),
                # 1 person has no location code
                (CategoryChoiceFilter._isnull, f"{_('Ingen')} (1)"),
            ],
        )

    def test_filter_on_isnull(self):
        filtered_qs = self.instance.filter(
            Person.objects.all(), CategoryChoiceFilter._isnull
        )
        self.assertQuerySetEqual(
            filtered_qs,
            Person.objects.filter(location_code__isnull=True),
        )


class TestPersonSearchView(PersonEnv):
    def setUp(self):
        super().setUp()
        self.view = PersonSearchView()
        self.view.setup(RequestFactory().get(""))

    def test_get_queryset_includes_padded_cpr(self):
        self.assertQuerySetEqual(
            self.view.get_queryset(),
            [person.cpr.zfill(10) for person in Person.objects.all()],
            transform=lambda obj: obj._cpr,
        )


class TimeContextMixin:
    view_class = None
    request_factory = RequestFactory()

    @property
    def view(self):
        view = self.view_class()
        request = self.request_factory.get("")
        view.setup(request, pk=self.person1.pk)
        with self._time_context():
            view.get(request, pk=self.person1.pk)
        return view

    def _time_context(self, year: int = 2020, month: int = 12):
        return patch("bf.views.timezone.now", return_value=datetime(year, month, 1))

    def _get_context_data(self):
        with self._time_context():
            return self.view.get_context_data()


class TestYearMonthMixin(TimeContextMixin, SimpleTestCase):
    class ImplView(YearMonthMixin, ContextMixin, View):
        """View implementation to use in tests"""

    request_factory = RequestFactory()

    def test_year_and_month_property_defaults(self):
        view = self._use_defaults()
        with self._time_context():
            self.assertEqual(view.year, 2020)
            self.assertEqual(view.month, 12)

    def test_year_and_month_query_parameters(self):
        # Act: 1. Test query parameters usage when year is current year
        with self._time_context(year=2020, month=6):
            view = self._use_query_parameters(2020, 1)
            self.assertEqual(view.year, 2020)
            # When `year` is current year, use the `month` provided in query params
            self.assertEqual(view.month, 1)

        # Act: 2. Test query parameters usage when year is before current year
        with self._time_context(year=2020, month=6):
            view = self._use_query_parameters(2019, 1)
            self.assertEqual(view.year, 2019)
            # When `year` is before current year, always use the last month of the year
            self.assertEqual(view.month, 12)

    def test_context_data_includes_year_and_month(self):
        view = self._use_defaults()
        with self._time_context(year=2020, month=12):
            context_data = view.get_context_data()
            self.assertEqual(context_data["year"], 2020)
            self.assertEqual(context_data["month"], 12)

    def _use_defaults(self) -> ImplView:
        view = self.ImplView()
        view.setup(self.request_factory.get(""))
        return view

    def _use_query_parameters(self, year: int, month: int) -> ImplView:
        view = self.ImplView()
        view.setup(
            self.request_factory.get("", data={"year": year, "month": month}),
            pk=0,
        )
        return view


class TestPersonDetailView(TimeContextMixin, PersonEnv):
    view_class = PersonDetailView

    def test_context_includes_key_figures(self):
        """The context must include the key figures for each person"""
        # Act
        context = self._get_context_data()
        # Assert: the context keys are present
        self.assertIn("total_estimated_year_result", context)
        self.assertIn("total_actual_year_result", context)
        self.assertIn("benefit_paid", context)
        # Assert: the key figures are correct
        self.assertEqual(
            context["total_estimated_year_result"],
            self._get_income_estimate_attr_sum("estimated_year_result"),
        )
        self.assertEqual(
            context["total_actual_year_result"],
            self._get_income_estimate_attr_sum("actual_year_result"),
        )
        self.assertEqual(context["benefit_paid"], sum(range(1, 13)))

    def _get_income_estimate_attr_sum(
        self, attr: str, year: int = 2020, month: int = 12
    ) -> Decimal:
        return (
            IncomeEstimate.objects.filter(
                person_month__person_year__person=self.person1,
                person_month__person_year__year__year=year,
                person_month__month=month,
            ).aggregate(sum=Sum(attr))
        )["sum"]


class TestPersonDetailBenefitView(TimeContextMixin, PersonEnv):
    view_class = PersonDetailBenefitView

    def test_context_includes_benefit_data(self):
        """The context data must include the `benefit_data` table"""
        # Act
        context = self._get_context_data()
        # Assert: the context key is present
        self.assertIn("benefit_data", context)
        # Assert: the table data is correct (one figure for each month)
        self.assertQuerySetEqual(
            context["benefit_data"],
            range(1, 13),
            transform=lambda obj: obj["benefit"],
            ordered=True,
        )

    def test_context_includes_benefit_chart(self):
        """The context data must include the `benefit_chart` chart"""
        self.assertIn("benefit_chart", self._get_context_data())

    def test_get_benefit_chart_series(self):
        """The `benefit chart` must consist of the expected series
        The "benefit chart" consists of two series:
        1. The benefit figures themselves (`PersonMonth.benefit_paid`) for each month.
        2. The estimated yearly income total (`IncomeEstimate.estimated_year_result`)
           for each month.
        """
        # Act
        with self._time_context():
            benefit_chart_series = self.view.get_all_benefit_chart_series()
        # Assert: verify the `benefit` series
        self.assertDictEqual(
            benefit_chart_series[0],
            {
                "data": [float(x) for x in range(1, 13)],
                "name": _("Beregnet beskæftigelsesfradrag"),
                "group": "benefit",
            },
        )
        # Assert: verify the `estimated_total_income` series
        self.assertDictEqual(
            benefit_chart_series[1],
            {
                "data": [float(x * 2 * 100) for x in range(1, 13)],
                "name": _("Estimeret samlet lønindkomst"),
                "group": "estimated_total_income",
                "type": "column",
            },
        )


class TestPersonDetailIncomeView(TimeContextMixin, PersonEnv):
    view_class = PersonDetailIncomeView

    def test_context_includes_income_per_employer_and_type(self):
        """The context must include the `income_per_employer_and_type` table"""
        # Act
        context = self._get_context_data()
        # Assert: the context key is present
        self.assertIn("income_per_employer_and_type", context)
        # Assert: the table data is correct (one yearly total for each employer/type)
        expected_total = Decimal(sum(x * 2 * 10 for x in range(1, 13)))
        self.assertListEqual(
            context["income_per_employer_and_type"],
            [
                {"source": "A-indkomst", "total_amount": expected_total},
                {"source": "B-indkomst", "total_amount": expected_total},
            ],
        )

    def test_context_includes_income_chart(self):
        """The context data must include the `income_chart` chart"""
        self.assertIn("income_chart", self._get_context_data())

    def test_get_income_chart_series(self):
        """The `income chart` must consist of the expected series.
        The "income chart" consists of N series, one series for each source of income
        that the person has had during the year.
        """
        # Act
        with self._time_context():
            income_chart_series = self.view.get_income_chart_series()
        # Assert: verify that we get the expected series: two A income series, and two
        # B income series (4 series total.)
        self.assertEqual(len(income_chart_series), 2)
        self.assertListEqual(
            income_chart_series,
            [
                {
                    "data": [float(x * 2 * 10) for x in range(1, 13)],
                    "name": name,
                    "group": "income",
                    "type": "column",
                }
                for name in (_("A-indkomst"), _("B-indkomst"))
            ],
        )
