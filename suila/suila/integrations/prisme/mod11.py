# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


def validate_mod11(cpr: str) -> bool:
    """Return True if `cpr` passes the "mod 11" test, otherwise return False."""
    # See https://da.wikipedia.org/wiki/Modulus_11
    # Note that the "modulus 11" test is no longer enforced by the CPR register.
    # But it is still enforced by older systems such as Prisme, and thus needs to be
    # handled when exporting data to Prisme.
    factors: list[int] = [4, 3, 2, 7, 6, 5, 4, 3, 2, 1]
    total: int = 0
    idx: int
    for idx, factor in enumerate(factors):
        digit: int = int(cpr[idx])
        total += digit * factor
    return total % 11 == 0
