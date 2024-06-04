from unittest.mock import patch
from django.test import TestCase

from bf.models import PersonMonth
from bf.management.commands.import_persons_from_eskat import Command
from eskat.models import ESkatMandtal


class TestImportPersonsFromESkat(TestCase):
    def setUp(self):
        super().setUp()
        self.command = Command()

    def test_handle(self):
        # Arrange
        mock_eskat_mandtal_objects = [
            ESkatMandtal(cpr="0101012222"),
        ]
        with patch(
            "bf.management.commands.import_persons_from_eskat.ESkatMandtal.objects.all",
            return_value=mock_eskat_mandtal_objects,
        ) as mock_eskat_mandtal:
            # Act
            self.command.handle()
            # Assert
            mock_eskat_mandtal.assert_called_once_with()
            self.assertQuerySetEqual(
                PersonMonth.objects.values_list("cpr", flat=True),
                [e.cpr for e in mock_eskat_mandtal_objects],
            )
