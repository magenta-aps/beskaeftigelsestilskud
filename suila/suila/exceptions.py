# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


class DependenciesNotMet(Exception):
    def __init__(self, name: str, dependency: str):
        super().__init__(f"'{dependency}' dependency for '{name}' is not met")


class BTaxFilesNotFound(Exception):
    def __init__(self, month=None):

        if month:
            error_message = f"There are no btax files for month={month}"
        else:
            error_message = "There are no new btax files"

        super().__init__(error_message)


class CalculationMethodNotSet(Exception):
    def __init__(self, year):
        error_message = f"calculation parameters for {year} are not set."
        super().__init__(error_message)
