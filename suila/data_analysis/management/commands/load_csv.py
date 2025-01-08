# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from datetime import date

from data_analysis.load import load_csv, type_map

from suila.management.commands.common import SuilaBaseCommand


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("file", type=str)
        parser.add_argument("type", type=str)
        parser.add_argument("year", type=int)
        parser.add_argument("--count", type=int)
        parser.add_argument("--delimiter", type=str, default=",")
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--show-multiyear-pks", type=int)
        super().add_arguments(parser)

    def _handle(self, *args, **kwargs):
        data_type = kwargs.get("type") or "income"
        keys = list(type_map.keys())
        if data_type not in keys:
            print(f"type skal være enten {', '.join(keys[:-1])} eller {keys[-1]}")
            return
        with open(kwargs["file"]) as input_stream:
            load_csv(
                input_stream,
                kwargs["file"],
                kwargs.get("year") or date.today().year,
                data_type,
                kwargs.get("count"),
                kwargs["delimiter"],
                kwargs.get("dry", True),
                self.stdout,
            )
