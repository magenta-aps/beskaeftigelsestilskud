# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Literal, TypeAlias

from suila.models import ManagementCommands

JOB_NAME: TypeAlias = Literal[
    ManagementCommands.CALCULATE_STABILITY_SCORE,
    ManagementCommands.AUTOSELECT_ESTIMATION_ENGINE,
    ManagementCommands.LOAD_ESKAT,
    ManagementCommands.LOAD_PRISME_B_TAX,
    ManagementCommands.IMPORT_U1A_DATA,
    ManagementCommands.GET_PERSON_INFO_FROM_DAFO,
    ManagementCommands.GET_UPDATED_PERSON_INFO_FROM_DAFO,
    ManagementCommands.ESTIMATE_INCOME,
    ManagementCommands.CALCULATE_BENEFIT,
    ManagementCommands.EXPORT_BENEFITS_TO_PRISME,
    ManagementCommands.SEND_EBOKS,
    ManagementCommands.LOAD_PRISME_BENEFITS_POSTING_STATUS,
]

JOB_TYPE: TypeAlias = Literal["yearly", "monthly", "daily"]
