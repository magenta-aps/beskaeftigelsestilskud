# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management import call_command
from django.db.models.functions import Length
from django.test import TestCase

from bf.management.commands.load_prisme_account_aliases import (
    Command as LoadPrismeAccountAliasesCommand,
)
from bf.models import PrismeAccountAlias


class TestLoadPrismeAccountAliases(TestCase):
    def setUp(self):
        super().setUp()
        self.command = LoadPrismeAccountAliasesCommand()

    def test_load_prisme_account_aliases(self):
        # Act
        call_command(self.command)
        # Assert: there are aliases for six municipalities across six tax years
        self.assertEqual(PrismeAccountAlias.objects.count(), 6 * 6)
        # Assert: all aliases have the expected length (37 digits)
        self.assertEqual(
            PrismeAccountAlias.objects.aggregate(
                lengths=ArrayAgg(Length("alias"), distinct=True)
            ),
            {"lengths": [37]},
        )
