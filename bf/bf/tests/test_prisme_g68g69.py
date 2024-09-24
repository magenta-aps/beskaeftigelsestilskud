# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import re
from datetime import date

from django.test import SimpleTestCase
from tenQ.writer.g68 import (
    G68Transaction,
    G68TransactionWriter,
    Posteringshenvisning,
    TransaktionstypeEnum,
    UdbetalingsberettigetIdentKodeEnum,
)
from tenQ.writer.g69 import G69TransactionWriter

from bf.integrations.prisme.g68g69 import G68G69TransactionPair, G68G69TransactionWriter


class TestG68G69TransactionWriter(SimpleTestCase):
    registreringssted: int = 0
    organisationsenhed: int = 9000
    maskinnummer: int = 99999

    posting_date: date = date(2024, 1, 27)
    payment_date: date = date(2024, 2, 1)

    def setUp(self):
        super().setUp()
        self._instance: G68G69TransactionWriter = G68G69TransactionWriter(
            0, self.organisationsenhed, self.maskinnummer
        )

    def test_init(self):
        # Assert class composition and inheritance is as expected
        self.assertIsInstance(self._instance, G68G69TransactionWriter)
        self.assertIsInstance(self._instance, G68TransactionWriter)
        self.assertIsInstance(
            self._instance._g69_transaction_writer, G69TransactionWriter
        )

        # Assert "registreringssted" is shared between both transaction writer instances
        self.assertEqual(self._instance.reg.val, self.registreringssted)
        self.assertEqual(
            self._instance._g69_transaction_writer.registreringssted,
            self.registreringssted,
        )

        # Assert "organisationsenhed" is shared between both transaction writer
        # instances.
        self.assertEqual(self._instance.org.val, self.organisationsenhed)
        self.assertEqual(
            self._instance._g69_transaction_writer.organisationsenhed,
            self.organisationsenhed,
        )

        # Assert "maskinnummer" is passed to underlying `G68TransactionWriter` instance
        self.assertEqual(self._instance.machine_id.val, self.maskinnummer)

    def test_serialize_transaction_pair(self):
        # Act
        pair: G68G69TransactionPair = self._instance.serialize_transaction_pair(
            TransaktionstypeEnum.AndenDestinationTilladt,
            UdbetalingsberettigetIdentKodeEnum.CPR,
            "3112700000",
            1000,
            self.payment_date,
            self.posting_date,
            "Some descriptive text",
        )

        # Assert
        self.assertIsInstance(pair, G68G69TransactionPair)

        # Assert that G68 "Posteringshenvisning" is equal to G69 "Udbetalingshenvisning"
        posteringshenvisning = None
        udbetalingshenvisning = None
        # Find "Posteringshenvisning" in G68
        fields = G68Transaction.parse(pair.g68)
        for field in fields:
            if isinstance(field, Posteringshenvisning):
                # Find "Udbetalingshenvisning" (field 117, 18 digits) in G69
                match = re.match(r".*&117(?P<val>\d{18}).*", pair.g69)
                if match is not None:
                    posteringshenvisning = field.val
                    udbetalingshenvisning = match.group("val")
                    self.assertEqual(posteringshenvisning, udbetalingshenvisning)
                    break
        else:  # loop fell through without finding a match
            self.fail(
                f"G68 `Posteringshenvisning` {posteringshenvisning} does not match "
                f"G69 `Udbetalingshenvisning` {udbetalingshenvisning}"
            )
