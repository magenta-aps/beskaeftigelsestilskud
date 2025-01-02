# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
from json import JSONEncoder
from typing import Type

from data_analysis.views import SimulationJSONEncoder
from ninja.renderers import JSONRenderer
from ninja_extra import NinjaExtraAPI

from bf.api.person import PersonAPI


class SuilaJSONRenderer(JSONRenderer):
    encoder_class: Type[JSONEncoder] = SimulationJSONEncoder


api = NinjaExtraAPI(
    title="Beskæftigelsestilskud", renderer=SuilaJSONRenderer(), csrf=False
)

api.register_controllers(PersonAPI)
