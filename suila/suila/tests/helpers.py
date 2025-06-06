# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase

from suila.models import Person, PersonMonth, PersonYear, Year


class ImportTestCase(TestCase):
    """Base class to help test Prisme SFTP imports"""

    encoding = "utf-16-le"

    @classmethod
    def add_person_month(
        cls,
        cpr: int,
        year: int = 2020,
        month: int = 1,
        benefit_calculated: Decimal = Decimal("1000.00"),
        benefit_transferred: Decimal = Decimal("1000.00"),
    ) -> PersonMonth:
        year, _ = Year.objects.get_or_create(year=year)
        person, _ = Person.objects.get_or_create(cpr=cpr)
        person_year, _ = PersonYear.objects.get_or_create(year=year, person=person)
        person_month, _ = PersonMonth.objects.get_or_create(
            person_year=person_year,
            month=month,
            import_date=date.today(),
            benefit_calculated=benefit_calculated,
            benefit_transferred=benefit_transferred,
        )
        return person_month

    @contextmanager
    def mock_sftp_server(self, *files):
        with patch(
            "suila.integrations.prisme.sftp_import.list_prisme_folder",
            # This causes N calls to `get_file_in_prisme_folder` to be made, where N is
            # the length of `files`.
            return_value=[f"filename{i}.csv" for i, _ in enumerate(files, start=1)],
        ):
            with patch(
                "suila.integrations.prisme.sftp_import.get_file_in_prisme_folder",
                # On each call to `get_file_in_prisme_folder`, provide a new return
                # value from this iterable.
                side_effect=[BytesIO(file.encode(self.encoding)) for file in files],
            ):
                yield

    @contextmanager
    def mock_sftp_server_folder(self, *files: tuple[str, str]):
        with patch(
            "suila.integrations.prisme.sftp_import.list_prisme_folder",
            # This causes N calls to `get_file_in_prisme_folder` to be made, where N is
            # the length of `files`.
            return_value=[filename for filename, contents in files],
        ):
            with patch(
                "suila.integrations.prisme.sftp_import.get_file_in_prisme_folder",
                # On each call to `get_file_in_prisme_folder`, provide a new return
                # value from this iterable.
                side_effect=[
                    BytesIO(contents.encode(self.encoding))
                    for filename, contents in files
                ],
            ):
                yield
