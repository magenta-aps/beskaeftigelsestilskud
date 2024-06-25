# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from data_analysis.models import CalculationResult
from data_analysis.views import (
    EmploymentListView,
    PersonAnalysisView,
    SimulationJSONEncoder,
)
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import TestCase
from django.test.client import RequestFactory

from bf.calculate import TwelveMonthsSummationEngine
from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear, Year
from bf.simulation import IncomeItem, Simulation


class TestSimulationJSONEncoder(TestCase):
    _person_serialized = {
        "address_line_1": None,
        "address_line_2": None,
        "address_line_3": None,
        "address_line_4": None,
        "address_line_5": None,
        "cpr": "",
        "full_address": None,
        "id": None,
        "name": None,
        "preferred_prediction_engine": "",
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
        model_instance = Person()
        self._assert_json_equal(model_instance, self._person_serialized)

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
            Person(),
            year=2020,
        )
        self._assert_json_equal(
            simulation, {"person": self._person_serialized, "rows": [], "year": 2020}
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
        cls._person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls._request_factory = RequestFactory()
        cls._view = PersonAnalysisView()

    def test_setup(self):
        self._view.setup(self._request_factory.get(""), pk=self._person.pk, year=2020)
        self.assertEqual(self._view.year, 2020)
        self.assertIsInstance(self._view.simulation, Simulation)
        self.assertEqual(self._view.simulation.year, 2020)
        self.assertEqual(self._view.simulation.person, self._person)

    def test_get_returns_json(self):
        self._view.setup(self._request_factory.get(""), pk=self._person.pk, year=2020)
        response = self._view.get(self._request_factory.get("?format=json"))
        self.assertIsInstance(response, HttpResponse)
        doc = json.loads(response.getvalue())
        self.assertEqual(doc["person"]["cpr"], "0101012222")
        self.assertEqual(doc["year"], 2020)

    def test_get_returns_html(self):
        self._view.setup(self._request_factory.get(""), pk=self._person.pk, year=2020)
        response = self._view.get(self._request_factory.get(""))
        self.assertIsInstance(response, TemplateResponse)


class TestEmploymentListView(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._person, _ = Person.objects.get_or_create(cpr="0101012222")
        cls._employer, _ = Employer.objects.get_or_create(cvr="1212122222")
        cls._year, _ = Year.objects.get_or_create(year=2020)
        cls._person_year, _ = PersonYear.objects.get_or_create(
            person=cls._person,
            year=cls._year,
        )
        cls._person_month, _ = PersonMonth.objects.get_or_create(
            person_year=cls._person_year,
            month=1,
            import_date=date(2020, 1, 1),
        )
        cls._a_salary_report, _ = ASalaryReport.objects.get_or_create(
            person_month=cls._person_month,
            employer=cls._employer,
            amount=42,
        )
        cls._calculation_result, _ = CalculationResult.objects.get_or_create(
            engine="EngineClassName",
            a_salary_report=cls._a_salary_report,
            actual_year_result=42,
            calculated_year_result=21,
        )
        cls._request_factory = RequestFactory()
        cls._view = EmploymentListView()

    def test_get(self):
        self._view.setup(self._request_factory.get(""), year=2020)
        response = self._view.get(self._request_factory.get(""))
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.context_data["year"], 2020)
        self.assertListEqual(
            response.context_data["object_list"],
            [
                {
                    "person": self._person,
                    "employer": self._employer,
                    "actual_sum": Decimal(self._a_salary_report.amount),
                    "EngineClassName": Decimal(50),
                }
            ],
        )
