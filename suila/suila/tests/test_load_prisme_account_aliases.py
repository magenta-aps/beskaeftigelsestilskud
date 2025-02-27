# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management import call_command
from django.db.models.functions import Length
from django.test import TestCase

from suila.management.commands.load_prisme_account_aliases import (
    Command as LoadPrismeAccountAliasesCommand,
)
from suila.models import PrismeAccountAlias


class TestLoadPrismeAccountAliases(TestCase):
    def setUp(self):
        super().setUp()
        self.command = LoadPrismeAccountAliasesCommand()

    def test_load_prisme_account_aliases(self):
        # Act
        call_command(self.command)
        # Assert: there are aliases for six municipalities across eight tax years
        self.assertEqual(PrismeAccountAlias.objects.count(), 6 * 8)
        # Assert: all aliases have the expected length (22 digits)
        self.assertEqual(
            PrismeAccountAlias.objects.aggregate(
                lengths=ArrayAgg(Length("alias"), distinct=True)
            ),
            {"lengths": [22]},
        )
