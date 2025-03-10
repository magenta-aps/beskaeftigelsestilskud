# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


class DependenciesNotMet(Exception):
    def __init__(self, name: str, dependency: str):
        super().__init__(f"'{dependency}' dependency for '{name}' is not met")
