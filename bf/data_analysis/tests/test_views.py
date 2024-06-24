import json
from decimal import Decimal
from unittest.mock import patch

from data_analysis.views import SimulationJSONEncoder
from django.test import TestCase

from bf.calculate import TwelveMonthsSummationEngine
from bf.models import Person
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
