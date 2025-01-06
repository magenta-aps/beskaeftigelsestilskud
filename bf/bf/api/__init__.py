# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
# mypy: disable-error-code="call-arg, attr-defined"
from json import JSONEncoder
from typing import Type

from common.utils import SuilaJSONEncoder
from ninja.renderers import JSONRenderer
from ninja_extra import NinjaExtraAPI

from bf.api.person import PersonAPI
from bf.api.personmonth import PersonMonthAPI
from bf.api.personyear import PersonYearAPI


class SuilaJSONRenderer(JSONRenderer):
    encoder_class: Type[JSONEncoder] = SuilaJSONEncoder


api = NinjaExtraAPI(
    title="Beskæftigelsestilskud", renderer=SuilaJSONRenderer(), csrf=False
)

api.register_controllers(PersonAPI, PersonYearAPI, PersonMonthAPI)
