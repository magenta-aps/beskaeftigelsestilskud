# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from bf.models import IncomeType, Person


class EstimationEngineUnset(Exception):
    def __init__(self, person: "Person"):
        self.person = person
        super().__init__(f"Preferred estimation engine is not set for person {person}")


class IncomeTypeUnhandledByEngine(Exception):
    def __init__(self, income_type: "IncomeType", engine: type):
        super().__init__(
            f"The income type {income_type} is not handled by {engine.__name__}"
        )
