# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import re
from decimal import ROUND_DOWN, Decimal


def get_amount_from_g68_content(g68_content):
    match = re.match(r".*&08(\d+)&.*", g68_content)

    if match:
        amount = Decimal(int(match.group(1)) / 100)

        # Assure 2 decimals
        return amount.quantize(Decimal("0.00"), rounding=ROUND_DOWN)
    else:
        raise ValueError(f"Could not extract amount from {g68_content}")
