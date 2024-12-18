# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from bf.management.commands.common import BfBaseCommand
from bf.models import EboksMessage


class Command(BfBaseCommand):

    def _handle(self, *args, **kwargs):
        EboksMessage.update_final_statuses()
