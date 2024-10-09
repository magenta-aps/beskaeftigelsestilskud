# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from cProfile import Profile
from datetime import date

from data_analysis.load import load_csv, type_map
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file", type=str)
        parser.add_argument("type", type=str)
        parser.add_argument("year", type=int)
        parser.add_argument("--count", type=int)
        parser.add_argument("--delimiter", type=str, default=",")
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--profile", action="store_true", default=False)
        parser.add_argument("--show-multiyear-pks", type=int)

    def _handle(self, *args, **kwargs):
        data_type = kwargs.get("type") or "income"
        keys = list(type_map.keys())
        if data_type not in keys:
            print(f"type skal være enten {', '.join(keys[:-1])} eller {keys[-1]}")
            return
        with open(kwargs["file"]) as input_stream:
            load_csv(
                input_stream,
                kwargs.get("year") or date.today().year,
                data_type,
                kwargs.get("count"),
                kwargs["delimiter"],
                kwargs.get("dry", True),
                self.stdout,
            )

    def handle(self, *args, **options):
        if options.get("profile", False):
            profiler = Profile()
            profiler.runcall(self._handle, *args, **options)
            profiler.print_stats(sort="tottime")
        else:
            self._handle(*args, **options)
