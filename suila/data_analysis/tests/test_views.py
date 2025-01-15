# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from common.models import EngineViewPreferences, User
from data_analysis.forms import PersonYearListOptionsForm
from data_analysis.views import (
    CalculatorView,
    HistogramView,
    JobListView,
    PersonAnalysisView,
    PersonListView,
    PersonYearEstimationMixin,
    SimulationJSONEncoder,
)
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import TestCase
from django.test.client import RequestFactory
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
        cls.year, _ = Year.objects.get_or_create(year=2020)
        PersonYear.objects.create(person=cls.person, year=cls.year)
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

        simulation = Simulation(
            [TwelveMonthsSummationEngine()],
            self.person,
            year_start=2020,
            year_end=2020,
            income_type=IncomeType.A,
        )
        self._assert_json_equal(
            simulation,
            {
                "person": self.person_serialized,
                "rows": [
                    {
                        "income_series": [],
                        "title": "Månedlig indkomst",
                        "chart_type": "bar",
                    },
                    {
                        "payout": [],
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


class TestPersonAnalysisView(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls.year, _ = Year.objects.get_or_create(year=2020)
        cls.middle_year, _ = Year.objects.get_or_create(year=2021)
        cls.other_year, _ = Year.objects.get_or_create(year=2022)
        cls.person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.year
        )
        cls.middle_person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.middle_year
        )
        cls.other_person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.other_year
        )
        cls.request_factory = RequestFactory()
        cls.view = PersonAnalysisView()

    def test_setup(self):
        request = self.request_factory.get("")
        self.view.setup(request, pk=self.person.pk)
        response = self.view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(self.view.year_start, 2022)
        self.assertEqual(self.view.year_end, 2022)

    def test_get_form_kwargs(self):
        request = self.request_factory.get("")
        self.view.setup(request, pk=self.person.pk, year=2020)
        self.view.get(request)
        form_kwargs = self.view.get_form_kwargs()
        self.assertEqual(form_kwargs["instance"], self.person)

    def test_invalid(self):
        request = self.request_factory.get("?income_type=foo")
        self.view.setup(request, pk=self.person.pk, year=2020)
        response = self.view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertFalse(response.context_data["form"].is_valid())

    def test_income_type(self):
        request = self.request_factory.get("?income_type=A")
        self.view.setup(request, pk=self.person.pk, year=2020)
        response = self.view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(self.view.income_type, IncomeType.A)

        request = self.request_factory.get("?income_type=B")
        self.view.setup(request, pk=self.person.pk, year=2020)
        response = self.view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(self.view.income_type, IncomeType.B)

        request = self.request_factory.get("?income_type=")
        self.view.setup(request, pk=self.person.pk, year=2020)
        response = self.view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertIsNone(self.view.income_type)


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


class ViewTestCase(TestCase):
    view_class = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._request_factory = RequestFactory()
        cls._view = cls.view_class()

        cls.user = User(cpr="0101011111")
        cls.user.save()

    def format_request(self, params=""):
        request = self._request_factory.get(params)
        request.user = self.user
        return request


class TestJobListView(ViewTestCase):
    view_class = JobListView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        JobLog.objects.create(
            name=ManagementCommands.CALCULATE_STABILITY_SCORE, cpr_param="111"
        )

    def test_get_returns_html(self):
        request = self.format_request()
        self._view.setup(request)
        response = self._view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].cpr_param, "111")


class TestPersonListView(PersonYearEstimationSetupMixin, ViewTestCase):
    view_class = PersonListView

    def test_get_returns_html(self):
        request = self.format_request()
        self._view.setup(request, year=2020)
        response = self._view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].amount_sum, Decimal(42))
        self.assertEqual(
            object_list[0].TwelveMonthsSummationEngine_mean_error_A, Decimal(0)
        )
        self.assertEqual(
            object_list[0].InYearExtrapolationEngine_mean_error_A, Decimal(50)
        )

    def test_get_no_results(self):
        request = self.format_request()
        self.estimate1.delete()
        self.estimate2.delete()
        self.summary1.mean_error_percent = Decimal(0)
        self.summary2.mean_error_percent = Decimal(0)
        self.summary1.save()
        self.summary2.save()
        self._view.setup(request, year=2020)
        response = self._view.get(request)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].amount_sum, Decimal("42.00"))
        self.assertEqual(
            object_list[0].TwelveMonthsSummationEngine_mean_error_A, Decimal(0)
        )
        self.assertEqual(
            object_list[0].InYearExtrapolationEngine_mean_error_A, Decimal(0)
        )

    def test_filter_no_a(self):
        request = self.format_request("?has_a=False")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_a(self):
        request = self.format_request("?has_a=True")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].actual_sum, Decimal(42))

    def test_filter_b(self):
        request = self.format_request("?has_b=True")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_no_b(self):
        request = self.format_request("?has_b=False")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
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
        request = self.format_request("?has_zero_income=False")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person.cpr, "0101012222")

        request = self.format_request("?has_zero_income=True")
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
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

        request = self.format_request(params)
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)

        params = f"?min_offset={self.summary2.mean_error_percent-1}"
        params += f"&max_offset={self.summary2.mean_error_percent+1}"
        params += "&selected_model=InYearExtrapolationEngine_mean_error_A"

        request = self.format_request(params)
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)

        params = f"?min_offset={self.summary1.mean_error_percent+1}"
        params += f"&max_offset={self.summary1.mean_error_percent+2}"
        params += "&selected_model=TwelveMonthsSummationEngine_mean_error_A"

        request = self.format_request(params)
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

        params = f"?min_offset={self.summary2.mean_error_percent+1}"
        params += f"&max_offset={self.summary2.mean_error_percent+2}"
        params += "&selected_model=InYearExtrapolationEngine_mean_error_A"

        request = self.format_request(params)
        self._view.setup(request, year=2020)
        response = self._view.get(request, year=2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_cpr(self):
        test_dict = {"0101012222": 1, "non_existing_number": 0}

        for cpr, expected_items in test_dict.items():
            request = self.format_request(f"?cpr={cpr}")
            self._view.setup(request, year=2020)
            response = self._view.get(request, year=2020)
            self.assertIsInstance(response, TemplateResponse)
            self.assertEqual(response.context_data["year"], 2020)
            object_list = response.context_data["object_list"]
            self.assertEqual(object_list.count(), expected_items)

    def test_get_queryset_invalid_form(self):
        form_mock = MagicMock()
        form_mock.is_valid.return_value = False
        self._view.get_form = MagicMock()
        self._view.get_form.return_value = form_mock

        self._view.kwargs = {"year": 2020}
        self._view.get_ordering = MagicMock()
        self._view.get_ordering.return_value = ["person_id"]
        self._view.get_queryset()
        form_mock.cleaned_data.get.assert_not_called()


class TestHistogramView(PersonYearEstimationSetupMixin, ViewTestCase):
    view_class = HistogramView

    def test_get_form_kwargs_populates_data_kwarg(self):
        tests = [
            ("", "10"),
            ("?resolution=10", "10"),
            ("?resolution=1", "1"),
        ]
        for query, resolution in tests:
            with self.subTest(f"resolution={resolution}"):
                self._view.setup(self._request_factory.get(query), year=2020)
                form_kwargs = self._view.get_form_kwargs()
                self.assertEqual(form_kwargs["data"]["resolution"], resolution)
                expected_year_url = self._view.form_class().get_year_url(self.year)
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
                self._view.setup(self._request_factory.get(query), year=2020)
                # self._view.get(self._request_factory.get(query), year=2020)
                self.assertEqual(self._view.get_resolution(), resolution)

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
                self._view.setup(self._request_factory.get(query), year=2020)
                self.assertEqual(self._view.get_metric(), metric)

    def test_get_income_type_from_form(self):
        tests = [
            ("", "A"),
            ("?income_type=A", "A"),
            ("?income_type=B", "B"),
            ("?income_type=C", "A"),
        ]
        for query, income_type in tests:
            with self.subTest(f"income_type={income_type}"):
                self._view.setup(self._request_factory.get(query), year=2020)
                self.assertEqual(self._view.get_income_type(), income_type)

    def test_get_returns_json(self):
        tests = [
            ("", 10),
            ("&resolution=10", 10),
            ("&resolution=1", 1),
        ]
        for query, resolution in tests:
            url = f"?format=json{query}&income_type=A"
            self._view.setup(self._request_factory.get(url), year=2020)
            response = self._view.get(self._request_factory.get(url))
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
        self._view.setup(self._request_factory.get(url), year=2020)
        response = self._view.get(self._request_factory.get(url))
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
        payload = {"show_SameAsLastMonthEngine": True}
        url = reverse("data_analysis:update_preferences", kwargs={"pk": self.user.pk})

        self.assertFalse(self.user.engine_view_preferences.show_SameAsLastMonthEngine)

        self.client.login(username="test", password="test")
        self.client.post(url, data=payload)
        self.user.refresh_from_db()

        self.assertTrue(self.user.engine_view_preferences.show_SameAsLastMonthEngine)


class TestCalculator(ViewTestCase):
    view_class = CalculatorView

    def request(self, amount):
        request = self._request_factory.post(
            path=reverse("data_analysis:calculator"),
            data={
                "estimated_year_income": amount,
                "method": "StandardWorkBenefitCalculationMethod",
                "benefit_rate_percent": "17.5",
                "personal_allowance": "58000.00",
                "standard_allowance": "10000",
                "max_benefit": "15750.00",
                "scaledown_rate_percent": "6.3",
                "scaledown_ceiling": "250000.00",
            },
        )
        self._view.setup(request)
        return self._view.post(request)

    def test_calculator_zero(self):
        response = self.request(0)
        self.assertIsInstance(response, TemplateResponse)
        self.assertTrue(response.context_data["form"].is_valid())
        self.assertEqual(response.context_data["result"], "0.00")
        self.assertEqual(response.context_data["result_monthly"], "0.00")
        self.assertJSONEqual(
            response.context_data["graph_points"],
            [
                [0.0, 0.0],
                [68000.0, 0.0],
                [158000.0, 15750.0],
                [250000.0, 15750.0],
                [500000.0, 0.0],
            ],
        )

    def test_calculator_ramp_up(self):
        response = self.request(100000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["result"], "5600.00")
        self.assertEqual(context["result_monthly"], "466.67")

    def test_calculator_ramp_plateau(self):
        response = self.request(250000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["result"], "15750.00")
        self.assertEqual(context["result_monthly"], "1312.50")

    def test_calculator_ramp_down(self):
        response = self.request(350000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["result"], "9450.00")
        self.assertEqual(context["result_monthly"], "787.50")

    def test_calculator_ramp_over(self):
        response = self.request(500000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["result"], "0.00")
        self.assertEqual(context["result_monthly"], "0.00")

    def test_get_engines(self):
        method = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.50"),
            personal_allowance=Decimal("60000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.30"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        Year.objects.create(year=2026, calculation_method=method)
        self.assertEqual(
            self._view.engines,
            [
                {
                    "name": "StandardWorkBenefitCalculationMethod for 2026",
                    "class": "StandardWorkBenefitCalculationMethod",
                    "fields": {
                        "benefit_rate_percent": {
                            "value": Decimal("17.500"),
                            "label": "Benefit rate percent",
                        },
                        "personal_allowance": {
                            "value": Decimal("60000.00"),
                            "label": "Personal allowance",
                        },
                        "standard_allowance": {
                            "value": Decimal("10000.00"),
                            "label": "Standard allowance",
                        },
                        "max_benefit": {
                            "value": Decimal("15750.00"),
                            "label": "Max benefit",
                        },
                        "scaledown_rate_percent": {
                            "value": Decimal("6.300"),
                            "label": "Scaledown rate percent",
                        },
                        "scaledown_ceiling": {
                            "value": Decimal("250000.00"),
                            "label": "Scaledown ceiling",
                        },
                    },
                }
            ],
        )
