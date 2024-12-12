# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from datetime import date

from tenQ.writer.g68 import (
    G68Transaction,
    G68TransactionWriter,
    Posteringshenvisning,
    TransaktionstypeEnum,
    UdbetalingsberettigetIdentKodeEnum,
)
from tenQ.writer.g69 import G69TransactionWriter


@dataclass(frozen=True, slots=True)
class G68G69TransactionPair:
    g68: str
    g69: str


class G68G69TransactionWriter(G68TransactionWriter):
    def __init__(
        self,
        registreringssted: int,
        organisationsenhed: int,
        maskinnummer: int | None = None,
    ):
        super().__init__(
            registreringssted,
            organisationsenhed,
            maskinnummer=maskinnummer,
        )
        self._g69_transaction_writer = G69TransactionWriter(
            registreringssted,
            organisationsenhed,
        )

    def serialize_transaction_pair(
        self,
        transaction_type: TransaktionstypeEnum,
        recipient_type: UdbetalingsberettigetIdentKodeEnum,
        recipient: str,
        account: int,
        amount: int,
        payment_date: date,
        posting_date: date,
        invoice_no: str,
        text: str,
    ) -> G68G69TransactionPair:
        # This also increments `self._line_no`
        g68_transaction_serialized = self.serialize_transaction(
            transaction_type,
            recipient_type,
            recipient,
            amount,
            payment_date,
            posting_date,
            invoice_no,
            text,
        )

        # Get the G68 "posteringshenvisning" ID
        g68_transaction_fields = list(G68Transaction.parse(g68_transaction_serialized))
        g69_udbetalingshenvisning = None
        for field in g68_transaction_fields:
            if isinstance(field, Posteringshenvisning):
                g69_udbetalingshenvisning = field.val

        # Build the G69 transaction, using:
        # - the G68 "posteringshenvisning" as the "udbetalingshenvisning",
        # - the G68 "maskinnummer" as the "maskinnummer",
        # - the G68 "linjeløbenummer" as the "ekspeditionsløbenummer"
        #   (== `self._line_no`),
        # - the G68 "posteringsdato" as the "posteringsdato".
        g69_transaction_serialized = self._g69_transaction_writer.serialize_transaction(
            udbet_henv_nr=int(g69_udbetalingshenvisning),  # type: ignore[arg-type]
            eks_løbenr=self._line_no,
            maskinnr=self.machine_id.val,
            kontonr=account,
            deb_kred="D",
            beløb=amount,
            post_dato=posting_date,
            ydelse_modtager=recipient,
            ydelse_modtager_nrkode=2,  # 02=CPR
        )

        return G68G69TransactionPair(
            g68=g68_transaction_serialized,
            g69=g69_transaction_serialized,
        )
