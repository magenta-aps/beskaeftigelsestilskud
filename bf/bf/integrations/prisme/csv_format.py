# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import csv
import re
from datetime import date
from io import BytesIO, TextIOWrapper
from typing import Self


class CSVFormat:
    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        raise NotImplementedError("must be implemented by subclass")  # pragma: no cover

    @classmethod
    def from_csv_buf(cls, buf: BytesIO, delimiter: str = ";") -> list[Self]:
        reader = csv.reader(TextIOWrapper(buf), delimiter=delimiter)
        return [cls.from_csv_row(row) for row in reader]

    @classmethod
    def parse_date(cls, val: str) -> date:
        match = re.match(r"(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})", val)
        if match:
            return date(
                *[int(match.group(field)) for field in ("year", "month", "day")]
            )
        raise ValueError(f"could not parse date {val!r}")
