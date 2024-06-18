# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0


from collections import defaultdict


def strtobool(val):
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


def get(item, field):
    if isinstance(item, dict):
        return item[field]
    if hasattr(item, field):
        return getattr(item, field)


def group(qs, field: str):
    groups = defaultdict(list)
    for item in qs:
        groups[get(item, field)].append(item)
    return groups
