# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from suila.management.commands.common import SuilaBaseCommand
from suila.models import EboksMessage


class Command(SuilaBaseCommand):
    filename = __file__

    def _handle(self, *args, **kwargs):
        EboksMessage.update_final_statuses()
