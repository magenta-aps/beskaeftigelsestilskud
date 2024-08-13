# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bf.models import Person


class EstimationEngineUnset(Exception):
    def __init__(self, person: "Person"):
        self.person = person
        super().__init__(f"Preferred estimation engine is not set for person {person}")
