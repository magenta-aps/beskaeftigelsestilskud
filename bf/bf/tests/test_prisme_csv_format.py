# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from django.test import SimpleTestCase

from bf.integrations.prisme.csv_format import CSVFormat

_EXAMPLE = "foobar;1234"


@dataclass(frozen=True)
class SampleFormat(CSVFormat):
    foo: str
    bar: int

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "SampleFormat":
        return cls(row[0], int(row[1]))


class TestCSVFormat(SimpleTestCase):
    def test_from_csv_buf(self):
        buf: BytesIO = BytesIO(_EXAMPLE.encode())
        rows = SampleFormat.from_csv_buf(buf)
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0], SampleFormat)

    def test_parse_date(self):
        parsed: date = CSVFormat.parse_date("2021/04/20")
        self.assertEqual(parsed, date(2021, 4, 20))

    def test_parse_date_raises_exception_on_invalid_input(self):
        with self.assertRaises(ValueError):
            CSVFormat.parse_date("")
