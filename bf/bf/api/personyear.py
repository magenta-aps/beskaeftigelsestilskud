# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"

from ninja import Field, ModelSchema

from bf.models import PersonYear


class PersonYearOut(ModelSchema):

    year: int = Field(q="year__year")

    class Config:
        model = PersonYear
        model_fields = [
            "preferred_estimation_engine_a",
            "preferred_estimation_engine_b",
            "tax_scope",
        ]
