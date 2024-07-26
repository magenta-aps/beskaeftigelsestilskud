# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from data_analysis.forms import PersonYearListOptionsForm
from data_analysis.views import (
    HistogramView,
    PersonAnalysisView,
    PersonListView,
    PersonYearEstimationMixin,
    SimulationJSONEncoder,
)
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import TestCase
from django.test.client import RequestFactory

from bf.estimation import InYearExtrapolationEngine, TwelveMonthsSummationEngine
from bf.models import (
    Employer,
    IncomeEstimate,
    MonthlyAIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearEstimateSummary,
    Year,
)
from bf.simulation import IncomeItem, Simulation


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
            "preferred_estimation_engine": None,
        }

    def test_can_serialize_dataclass(self):
        dataclass_instance = IncomeItem(year=2020, month=1, value=Decimal("42"))
        self._assert_json_equal(
            dataclass_instance,
            {"year": 2020, "month": 1, "value": 42},
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
            year=2020,
        )
        self._assert_json_equal(
            simulation,
            {
                "person": self.person_serialized,
                "rows": [{"income_series": [], "income_sum": 0.0, "predictions": []}],
                "year": 2020,
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
        self.assertJSONEqual(
            json.dumps(obj, cls=SimulationJSONEncoder),
            expected_data,
        )


class TestPersonAnalysisView(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls.year, _ = Year.objects.get_or_create(year=2020)
        cls.person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person, year=cls.year
        )
        cls._request_factory = RequestFactory()
        cls._view = PersonAnalysisView()

    def test_setup(self):
        self._view.setup(self._request_factory.get(""), pk=self.person.pk, year=2020)
        self.assertEqual(self._view.year, 2020)
        self.assertIsInstance(self._view.simulation, Simulation)
        self.assertEqual(self._view.simulation.year, 2020)
        self.assertEqual(self._view.simulation.person, self.person)

    def test_get_returns_json(self):
        self._view.setup(self._request_factory.get(""), pk=self.person.pk, year=2020)
        response = self._view.get(self._request_factory.get("?format=json"))
        self.assertIsInstance(response, HttpResponse)
        doc = json.loads(response.getvalue())
        self.assertEqual(doc["person"]["cpr"], "0101012222")
        self.assertEqual(doc["year"], 2020)

    def test_get_returns_html(self):
        self._view.setup(self._request_factory.get(""), pk=self.person.pk, year=2020)
        response = self._view.get(self._request_factory.get(""))
        self.assertIsInstance(response, TemplateResponse)

    def test_get_form_kwargs(self):
        self._view.setup(self._request_factory.get(""), pk=self.person.pk, year=2020)
        form_kwargs = self._view.get_form_kwargs()
        self.assertEqual(form_kwargs["year"], 2020)


class PersonYearEstimationSetupMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls.employer, _ = Employer.objects.get_or_create(cvr="1212122222")
        cls.year, _ = Year.objects.get_or_create(year=2020)
        cls.person_year, _ = PersonYear.objects.get_or_create(
            person=cls.person,
            year=cls.year,
        )
        cls.person_month, _ = PersonMonth.objects.get_or_create(
            person_year=cls.person_year,
            month=1,
            import_date=date(2020, 1, 1),
        )
        cls.a_income_report, _ = MonthlyAIncomeReport.objects.get_or_create(
            person_month=cls.person_month,
            employer=cls.employer,
            amount=42,
            month=cls.person_month.month,
            year=cls.year.year,
            person=cls.person,
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
            offset_percent=Decimal(0),
        )
        cls.summary2, _ = PersonYearEstimateSummary.objects.get_or_create(
            person_year=cls.person_year,
            estimation_engine=InYearExtrapolationEngine.__name__,
            offset_percent=Decimal(50),
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
        self.summary2.offset_percent = Decimal(50)
        self.summary2.save()

        # Act
        result = self._instance.get_queryset()
        # Assert
        self.assertQuerySetEqual(
            result,
            PersonYear.objects.all(),
        )
        # Assert: verify correct offset for "normal" month
        self.assertEqual(result[0].InYearExtrapolationEngine, Decimal("50"))
        # Assert: verify correct offset for month containing zero
        self.assertEqual(result[0].TwelveMonthsSummationEngine, Decimal("0"))


class ViewTestCase(TestCase):
    view_class = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._request_factory = RequestFactory()
        cls._view = cls.view_class()


class TestPersonListView(PersonYearEstimationSetupMixin, ViewTestCase):
    view_class = PersonListView

    def test_get_returns_html(self):
        self._view.setup(self._request_factory.get(""), year=2020)
        response = self._view.get(self._request_factory.get(""))
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].amount_sum, Decimal(42))
        self.assertEqual(object_list[0].TwelveMonthsSummationEngine, Decimal(0))
        self.assertEqual(object_list[0].InYearExtrapolationEngine, Decimal(50))

    def test_get_no_results(self):
        self.estimate1.delete()
        self.estimate2.delete()
        self.summary1.offset_percent = Decimal(0)
        self.summary2.offset_percent = Decimal(0)
        self.summary1.save()
        self.summary2.save()
        self._view.setup(self._request_factory.get(""), year=2020)
        response = self._view.get(self._request_factory.get(""))
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)
        self.assertEqual(object_list[0].person, self.person)
        self.assertEqual(object_list[0].amount_sum, Decimal("42.00"))
        self.assertEqual(object_list[0].TwelveMonthsSummationEngine, Decimal(0))
        self.assertEqual(object_list[0].InYearExtrapolationEngine, Decimal(0))

    def test_filter_no_a(self):
        self._view.setup(
            self._request_factory.get("?has_a=False&has_b=True"), year=2020
        )
        response = self._view.get(self._request_factory.get(""), year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 0)

    def test_filter_a(self):
        self._view.setup(
            self._request_factory.get("?has_a=True&has_b=False"), year=2020
        )
        response = self._view.get(self._request_factory.get(""), year=2020)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        object_list = response.context_data["object_list"]
        self.assertEqual(object_list.count(), 1)


class TestHistogramView(PersonYearEstimationSetupMixin, ViewTestCase):
    view_class = HistogramView

    def test_get_form_kwargs_populates_data_kwarg(self):
        tests = [
            ("", "10"),
            ("?resolution=10", "10"),
            ("?resolution=1", "1"),
        ]
        for query, percentile_size in tests:
            with self.subTest(f"resolution={percentile_size}"):
                self._view.setup(self._request_factory.get(query), year=2020)
                form_kwargs = self._view.get_form_kwargs()
                self.assertEqual(form_kwargs["data"]["resolution"], percentile_size)
                expected_year_url = self._view.form_class().get_year_url(self.year)
                self.assertEqual(form_kwargs["data"]["year"], expected_year_url)

    def test_get_percentile_size_from_form(self):
        tests = [
            ("", 10),
            ("?resolution=10", 10),
            ("?resolution=1", 1),
            ("?resolution=invalid", 10),
        ]
        for query, percentile_size in tests:
            with self.subTest(f"resolution={percentile_size}"):
                self._view.setup(self._request_factory.get(query), year=2020)
                # self._view.get(self._request_factory.get(query), year=2020)
                self.assertEqual(self._view.get_percentile_size(), percentile_size)

    def test_get_returns_json(self):
        tests = [
            ("", 10),
            ("&resolution=10", 10),
            ("&resolution=1", 1),
        ]
        for query, percentile_size in tests:
            with self.subTest(f"resolution={percentile_size}"):
                url = f"?format=json{query}"
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
                                size=percentile_size,
                            ),
                            "TwelveMonthsSummationEngine": self._get_expected_histogram(
                                "0",
                                1,
                                size=percentile_size,
                            ),
                        },
                        "percentile_size": percentile_size,
                    },
                )

    def _get_expected_histogram(self, bucket, count, size=10):
        data = dict.fromkeys([str(bucket) for bucket in range(0, 100, size)], 0)
        data[bucket] = count
        return data
