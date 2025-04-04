# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from common.models import EngineViewPreferences, PageView, User
from common.tests.test_mixins import TestViewMixin
from data_analysis.forms import PersonYearListOptionsForm
from data_analysis.views import (
    HistogramView,
    JobListView,
    PersonAnalysisView,
    PersonListView,
    PersonYearEstimationMixin,
    SimulationJSONEncoder,
)
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import TestCase
from django.urls import reverse

from suila.estimation import InYearExtrapolationEngine, TwelveMonthsSummationEngine
from suila.models import (
    IncomeEstimate,
    IncomeType,
    JobLog,
    ManagementCommands,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
    StandardWorkBenefitCalculationMethod,
    Year,
)
from suila.simulation import IncomeItem, IncomeItemValuePart, Simulation


class TestSimulationJSONEncoder(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create()
        cls.calculation_method = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )

        cls.year = Year.objects.create(
            year=2020, calculation_method=cls.calculation_method
        )
        cls.personyear = PersonYear.objects.create(person=cls.person, year=cls.year)
        cls.person_serialized = {
            "address_line_1": None,
            "address_line_2": None,
            "address_line_3": None,
            "address_line_4": None,
            "address_line_5": None,
            "cpr": "",
            "full_address": None,
            "id": cls.person.pk,
            "name": None,
            "civil_state": None,
            "location_code": None,
            "foreign_address": None,
            "country_code": None,
        }
        cls.personyear_serialized = {
            "id": cls.personyear.pk,
            "person_id": cls.person.pk,
            "preferred_estimation_engine_a": "InYearExtrapolationEngine",
            "preferred_estimation_engine_u": "TwelveMonthsSummationEngine",
            "stability_score_a": None,
            "stability_score_b": None,
            "tax_scope": "FULD",
            "year_id": 2020,
            "b_expenses": 0.0,
            "b_income": 0.0,
            "catchsale_expenses": 0.0,
            "paused": False,
        }

    def test_can_serialize_dataclass(self):
        dataclass_instance = IncomeItem(
            year=2020,
            month=1,
            value=Decimal("42"),
            value_parts=[
                IncomeItemValuePart(income_type=IncomeType.A, value=Decimal("42"))
            ],
        )
        self._assert_json_equal(
            dataclass_instance,
            {
                "year": 2020,
                "month": 1,
                "value": 42,
                "value_parts": [
                    {
                        "income_type": "A",
                        "value": 42,
                    }
                ],
            },
        )

    def test_can_serialize_decimal(self):
        decimal_instance = Decimal("42")
        self._assert_json_equal(decimal_instance, 42)

    def test_can_serialize_model(self):
        self._assert_json_equal(self.person, self.person_serialized)
        self._assert_json_equal(self.personyear, self.personyear_serialized)

    def test_can_serialize_calculation_engine(self):
        engine = TwelveMonthsSummationEngine()
        self._assert_json_equal(
            engine,
            {
                "class": engine.__class__.__name__,
                "description": TwelveMonthsSummationEngine.description,
            },
        )

    def test_can_serialize_simulation(self):
        self.maxDiff = None

        a_income_simulation = Simulation(
            [TwelveMonthsSummationEngine()],
            self.person,
            year_start=2020,
            year_end=2020,
            income_type=IncomeType.A,
        )
        self._assert_json_equal(
            a_income_simulation,
            {
                "person": self.person_serialized,
                "rows": [
                    {
                        "income_series": [],
                        "title": "Månedlig indkomst",
                        "chart_type": "bar",
                    },
                    {
                        "payout": [
                            {
                                "correct_payout": 0.0,
                                "cumulative_payout": 0.0,
                                "estimated_year_benefit": 0.0,
                                "estimated_year_result": 0.0,
                                "month": m,
                                "payout": 0.0,
                                "year": 2020,
                            }
                            for m in range(1, 13)
                        ],
                        "title": "Månedlig udbetaling",
                        "chart_type": "line",
                    },
                    {
                        "income_sum": {"2020": 0.0},
                        "predictions": [],
                        "title": "TwelveMonthsSummationEngine"
                        " - Summation af beløb for de seneste 12 måneder",
                        "chart_type": "line",
                    },
                ],
                "year_start": 2020,
                "year_end": 2020,
                "calculation_methods": None,
            },
        )

        u_income_simulation = Simulation(
            [TwelveMonthsSummationEngine()],
            self.person,
            year_start=2020,
            year_end=2020,
            income_type=IncomeType.U,
        )
        self._assert_json_equal(
            u_income_simulation,
            {
                "person": self.person_serialized,
                "rows": [
                    {
                        "income_series": [],
                        "title": "Månedlig indkomst",
                        "chart_type": "bar",
                    },
                    {
                        "payout": [
                            {
                                "correct_payout": 0.0,
                                "cumulative_payout": 0.0,
                                "estimated_year_benefit": 0.0,
                                "estimated_year_result": 0.0,
                                "month": m,
                                "payout": 0.0,
                                "year": 2020,
                            }
                            for m in range(1, 13)
                        ],
                        "title": "Månedlig udbetaling",
                        "chart_type": "line",
                    },
                    {
                        "income_sum": {"2020": 0.0},
                        "predictions": [],
                        "title": "TwelveMonthsSummationEngine"
                        " - Summation af beløb for de seneste 12 måneder",
                        "chart_type": "line",
                    },
                ],
                "year_start": 2020,
                "year_end": 2020,
                "calculation_methods": None,
            },
        )

    def test_calls_super_class_default(self):
        """Verify that `SimulationJSONEncoder` calls `super().default(...) on any other
        datatype.
        """
        instance = SimulationJSONEncoder()
        with patch(
            "data_analysis.views.DjangoJSONEncoder.default"
        ) as mock_super_default:
            instance.default(42)
            mock_super_default.assert_called_once_with(42)

    def _assert_json_equal(self, obj, expected_data):
        actual = json.dumps(obj, cls=SimulationJSONEncoder)
        try:
            self.assertJSONEqual(actual, expected_data)
        except AssertionError:
            print(actual)
            raise


class TestPersonAnalysisView(TestViewMixin, TestCase):
    view_class = PersonAnalysisView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person = Person.objects.create(cpr="0101012222")
        cls.calculation_method = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        cls.year = Year.objects.create(
            year=2020, calculation_method=cls.calculation_method
        )
        cls.middle_year = Year.objects.create(
            year=2021, calculation_method=cls.calculation_method
        )
        cls.other_year = Year.objects.create(
            year=2022, calculation_method=cls.calculation_method
        )
        cls.person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.year
        )
        cls.middle_person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.middle_year
        )
        cls.other_person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.other_year
        )

    def test_setup(self):
        view, response = self.request_get(self.admin_user, "", pk=self.person.pk)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(view.year_start, 2022)
        self.assertEqual(view.year_end, 2022)

    def test_get_form_kwargs(self):
        view, response = self.request_get(
            self.admin_user, "", pk=self.person.pk, year=2020
        )
        form_kwargs = view.get_form_kwargs()
        self.assertEqual(form_kwargs["instance"], self.person)

    def test_invalid(self):
        view, response = self.request_get(
            self.admin_user, "?income_type=foo", pk=self.person.pk, year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertFalse(response.context_data["form"].is_valid())

    def test_income_type(self):
        view, response = self.request_get(
            self.admin_user, "?income_type=A", pk=self.person.pk, year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(view.income_type, IncomeType.A)

        view, response = self.request_get(
            self.admin_user, "?income_type=B", pk=self.person.pk, year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(view.income_type, IncomeType.B)

        view, response = self.request_get(
            self.admin_user, "?income_type=", pk=self.person.pk, year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertIsNone(view.income_type)

    def test_view_borger_denied(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.normal_user, "", pk=self.person.pk)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", pk=self.person.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"person/{self.person.pk}/?year_start=2020&year_end=2022",
            pk=self.person.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonAnalysisView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person.pk})
        self.assertEqual(pageview.params, {"year_start": "2020", "year_end": "2022"})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 3)
        self.assertEqual(
            {itemview.item for itemview in itemviews},
            {self.person_year, self.middle_person_year, self.other_person_year},
        )


class PersonYearEstimationSetupMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls.year, _ = Year.objects.get_or_create(year=2020)
        cls.person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person,
            year=cls.year,
        )
        cls.person_month, _ = PersonMonth.objects.get_or_create(
            person_year=cls.person_year,
            month=1,
            import_date=date(2020, 1, 1),
            actual_year_benefit=200,
            benefit_paid=150,
        )
        cls.income_report, _ = MonthlyIncomeReport.objects.get_or_create(
            person_month=cls.person_month,
            salary_income=42,
            month=cls.person_month.month,
            year=cls.year.year,
        )
        cls.estimate1, _ = IncomeEstimate.objects.get_or_create(
            engine=TwelveMonthsSummationEngine.__name__,
            actual_year_result=42,
            estimated_year_result=42,
            person_month=cls.person_month,
        )
        cls.estimate2, _ = IncomeEstimate.objects.get_or_create(
            engine=InYearExtrapolationEngine.__name__,
            actual_year_result=42,
            estimated_year_result=21,
            person_month=cls.person_month,
        )
        cls.summary1, _ = PersonYearEstimateSummary.objects.get_or_create(
            person_year=cls.person_year,
            estimation_engine=TwelveMonthsSummationEngine.__name__,
            mean_error_percent=Decimal(0),
            income_type=IncomeType.A,
        )
        cls.summary2, _ = PersonYearEstimateSummary.objects.get_or_create(
            person_year=cls.person_year,
            estimation_engine=InYearExtrapolationEngine.__name__,
            mean_error_percent=Decimal(50),
            income_type=IncomeType.A,
        )


class TestPersonYearEstimationMixin(PersonYearEstimationSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._instance = PersonYearEstimationMixin()
        cls._instance.kwargs = {"year": 2020}
        cls._form = PersonYearListOptionsForm(data={})
        cls._instance.get_form = lambda: cls._form

    def test_handles_actual_year_income_zero(self):
        """Verify that we handle a person month where the recorded actual year income
        is zero.
        This is a regression test showing that we do not encounter a division by zero
        in such cases.
        """
        # Arrange: create a new person month
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=self.person_year,
            month=2,
            import_date=date(2020, 1, 1),
        )
        # Arrange: give this person month an actual year result of 0
        IncomeEstimate.objects.get_or_create(
            engine=TwelveMonthsSummationEngine.__name__,
            actual_year_result=0,
            estimated_year_result=100,
            person_month=person_month,
        )
        self.summary2.mean_error_percent = Decimal(50)
        self.summary2.save()

        # Act
        result = self._instance.get_queryset()
        # Assert
        self.assertQuerySetEqual(
            result,
            PersonYear.objects.all(),
        )
        # Assert: verify correct offset for "normal" month
        self.assertEqual(
            result[0].InYearExtrapolationEngine_mean_error_A, Decimal("50")
        )
        # Assert: verify correct offset for month containing zero
        self.assertEqual(
            result[0].TwelveMonthsSummationEngine_mean_error_A, Decimal("0")
        )

    def test_get_queryset_invalid_form(self):

        form_mock = MagicMock()
        form_mock.is_valid.return_value = False
        self._instance.get_form = MagicMock()
        self._instance.get_form.return_value = form_mock

        qs = self._instance.get_queryset()
        self.assertNotIn("a_count", dir(qs[0]))
        self.assertNotIn("b_count", dir(qs[0]))

    def test_get_queryset_no_min_max_offset(self):
        qs1 = self._instance.get_queryset()

        self._form = PersonYearListOptionsForm(
            data={
                "selected_model": "InYearExtrapolationEngine_mean_error_A",
                "min_offset": None,
                "max_offset": None,
            }
        )
        self._instance.get_form = lambda: self._form
        qs2 = self._instance.get_queryset()

        self.assertEqual(list(qs1), list(qs2))


class TestJobListView(TestViewMixin, TestCase):
    view_class = JobListView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.joblog = JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE, cpr_param="111"
        )

    def test_get_returns_html(self):
        view, response = self.request_get(self.admin_user, "")
        self.assertIsInstance(response, TemplateResponse)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].cpr_param, "111")

    def test_view_borger_denied(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.normal_user, "")

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(self.admin_user, "")
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "JobListView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {})
        self.assertEqual(pageview.params, {})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.joblog)


class TestPersonListView(PersonYearEstimationSetupMixin, TestViewMixin, TestCase):
    view_class = PersonListView

    def test_get_returns_html(self):
        view, response = self.request_get(self.admin_user, "", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(
            object_list[0].TwelveMonthsSummationEngine_mean_error_A, Decimal(0)
        )
        self.assertEqual(
            object_list[0].InYearExtrapolationEngine_mean_error_A, Decimal(50)
        )

    def test_get_no_results(self):
        self.estimate1.delete()
        self.estimate2.delete()
        self.summary1.mean_error_percent = Decimal(0)
        self.summary2.mean_error_percent = Decimal(0)
        self.summary1.save()
        self.summary2.save()
        view, response = self.request_get(self.admin_user, "", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(
            object_list[0].TwelveMonthsSummationEngine_mean_error_A, Decimal(0)
        )
        self.assertEqual(
            object_list[0].InYearExtrapolationEngine_mean_error_A, Decimal(0)
        )

    def test_filter_no_a(self):
        view, response = self.request_get(self.admin_user, "?has_a=False", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_a(self):
        view, response = self.request_get(self.admin_user, "?has_a=True", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].actual_sum, Decimal(42))

    def test_filter_b(self):
        view, response = self.request_get(self.admin_user, "?has_b=True", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_no_b(self):
        view, response = self.request_get(self.admin_user, "?has_b=False", year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].actual_sum, Decimal(42))

    def test_filter_no_income(self):
        person2, _ = Person.objects.get_or_create(cpr="0101012223")
        person_year2, _ = PersonYear.objects.get_or_create(
            person=person2, year=self.year
        )
        person_month2, _ = PersonMonth.objects.get_or_create(
            person_year=person_year2,
            month=1,
            import_date=date(2020, 1, 1),
            actual_year_benefit=0,
            benefit_paid=0,
        )

        view, response = self.request_get(
            self.admin_user, "?has_zero_income=False", year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person.cpr, "0101012222")

        view, response = self.request_get(
            self.admin_user, "?has_zero_income=True", year=2020
        )
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 2)
        self.assertEqual(object_list[0].person.cpr, "0101012222")
        self.assertEqual(object_list[1].person.cpr, "0101012223")

    def test_filter_min_max_offset(self):

        params = f"?min_offset={self.summary1.mean_error_percent-1}"
        params += f"&max_offset={self.summary1.mean_error_percent+1}"
        params += "&selected_model=TwelveMonthsSummationEngine_mean_error_A"
        view, response = self.request_get(self.admin_user, params, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)

        params = f"?min_offset={self.summary2.mean_error_percent-1}"
        params += f"&max_offset={self.summary2.mean_error_percent+1}"
        params += "&selected_model=InYearExtrapolationEngine_mean_error_A"
        view, response = self.request_get(self.admin_user, params, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)

        params = f"?min_offset={self.summary1.mean_error_percent+1}"
        params += f"&max_offset={self.summary1.mean_error_percent+2}"
        params += "&selected_model=TwelveMonthsSummationEngine_mean_error_A"
        view, response = self.request_get(self.admin_user, params, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

        params = f"?min_offset={self.summary2.mean_error_percent+1}"
        params += f"&max_offset={self.summary2.mean_error_percent+2}"
        params += "&selected_model=InYearExtrapolationEngine_mean_error_A"
        view, response = self.request_get(self.admin_user, params, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_cpr(self):
        test_dict = {"0101012222": 1, "non_existing_number": 0}

        for cpr, expected_items in test_dict.items():
            view, response = self.request_get(self.admin_user, f"?cpr={cpr}", year=2020)
            self.assertIsInstance(response, TemplateResponse)
            self.assertEqual(response.context_data["year"], 2020)
            object_list = response.context_data["object_list"]
            self.assertEqual(object_list.count(), expected_items)

    def test_get_queryset_invalid_form(self):
        form_mock = MagicMock()
        form_mock.is_valid.return_value = False
        view = self.view()
        view.get_form = MagicMock()
        view.get_form.return_value = form_mock

        view.kwargs = {"year": 2020}
        view.get_ordering = MagicMock()
        view.get_ordering.return_value = ["person_id"]
        view.get_queryset()
        form_mock.cleaned_data.get.assert_not_called()

    def test_view_borger_denied(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.normal_user, "", year=2020)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", year=2020)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(self.admin_user, "", year=2020)
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonListView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"year": 2020})
        self.assertEqual(pageview.params, {})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.person_year)


class TestHistogramView(PersonYearEstimationSetupMixin, TestViewMixin, TestCase):
    view_class = HistogramView

    def test_get_form_kwargs_populates_data_kwarg(self):
        tests = [
            ("", "10"),
            ("?resolution=10", "10"),
            ("?resolution=1", "1"),
        ]
        for query, resolution in tests:
            with self.subTest(f"resolution={resolution}"):
                view, response = self.request_get(self.admin_user, query, year=2020)
                form_kwargs = view.get_form_kwargs()
                self.assertEqual(form_kwargs["data"]["resolution"], resolution)
                expected_year_url = view.form_class().get_year_url(self.year)
                self.assertEqual(form_kwargs["data"]["year"], expected_year_url)

    def test_get_resolution_from_form(self):
        tests = [
            ("", 10),
            ("?resolution=10", 10),
            ("?resolution=1", 1),
            ("?resolution=invalid", 10),
        ]
        for query, resolution in tests:
            with self.subTest(f"resolution={resolution}"):
                view, response = self.request_get(self.admin_user, query, year=2020)
                # self._view.get(self._request_factory.get(query), year=2020)
                self.assertEqual(view.get_resolution(), resolution)

    def test_get_metric_from_form(self):
        tests = [
            ("", "mean_error"),
            ("?metric=mean_error", "mean_error"),
            ("?metric=rmse", "rmse"),
            ("?metric=payout_offset", "payout_offset"),
            ("?metric=invalid", "mean_error"),
        ]
        for query, metric in tests:
            with self.subTest(f"metric={metric}"):
                view, response = self.request_get(self.admin_user, query, year=2020)
                self.assertEqual(view.get_metric(), metric)

    def test_get_income_type_from_form(self):
        tests = [
            ("", "A"),
            ("?income_type=A", "A"),
            ("?income_type=B", "B"),
            ("?income_type=C", "A"),
        ]
        for query, income_type in tests:
            with self.subTest(f"income_type={income_type}"):
                view, response = self.request_get(self.admin_user, query, year=2020)
                self.assertEqual(view.get_income_type(), income_type)

    def test_get_returns_json(self):
        tests = [
            ("", 10),
            ("&resolution=10", 10),
            ("&resolution=1", 1),
        ]
        for query, resolution in tests:
            url = f"?format=json{query}&income_type=A"
            view, response = self.request_get(self.admin_user, url, year=2020)
            self.assertIsInstance(response, HttpResponse)

            self.assertJSONEqual(
                response.content,
                {
                    "data": {
                        "InYearExtrapolationEngine": self._get_expected_histogram(
                            "50",
                            1,
                            size=resolution,
                        ),
                        "TwelveMonthsSummationEngine": self._get_expected_histogram(
                            "0",
                            1,
                            size=resolution,
                        ),
                    },
                    "resolution": resolution,
                    "unit": "%",
                },
            )

    def test_payout_offset_histogram(self):
        url = "?format=json&resolution=200&metric=payout_offset"
        view, response = self.request_get(self.admin_user, url, year=2020)
        self.assertIsInstance(response, HttpResponse)

        self.assertJSONEqual(
            response.content,
            {
                "data": {
                    "payout_offset": self._get_expected_histogram(
                        "0",
                        1,
                        size=200,
                    ),
                },
                "resolution": 200,
                "unit": "kr",
            },
        )

    def _get_expected_histogram(self, bucket, count, size=10):
        data = dict.fromkeys([str(bucket) for bucket in range(0, 100, size)], 0)
        data[bucket] = count
        return data

    def test_view_borger_denied(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.normal_user, "", year=2020)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", year=2020)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            "2020/histogram/",
            year=2020,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "HistogramView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"year": 2020})
        self.assertEqual(pageview.params, {})
        self.assertEqual(pageview.itemviews.count(), 0)


class TestUpdateEngineViewPreferences(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(
            username="test",
            password="test",
            email="test@test.com",
            cpr="0101011111",
        )

        cls.preferences = EngineViewPreferences(user=cls.user)
        cls.preferences.save()

    def test_preferences_updater(self):
        payload = {"show_MonthlyContinuationEngine": True}
        url = reverse("data_analysis:update_preferences")
        self.assertFalse(
            self.user.engine_view_preferences.show_MonthlyContinuationEngine
        )
        self.client.login(username="test", password="test")
        self.client.post(url, data=payload)
        self.user.refresh_from_db()
        self.assertTrue(
            self.user.engine_view_preferences.show_MonthlyContinuationEngine
        )
