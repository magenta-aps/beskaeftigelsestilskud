# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.core.management.commands import makemessages


class Command(makemessages.Command):
    msgmerge_options = list(
        {*makemessages.Command.msgmerge_options, "--no-fuzzy-matching"}
    )
