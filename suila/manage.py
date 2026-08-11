#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

"""Django's command-line utility for administrative tasks."""
import multiprocessing
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    # Python 3.14 changed the default multiprocessing start method on Linux from
    # "fork" to "forkserver". Django's parallel test runner only supports "fork"
    # and "spawn": under "forkserver" `--parallel` silently degrades to a single
    # process (see django.test.runner.get_max_test_processes), so the whole test
    # suite runs serially. Request "fork" explicitly to keep `--parallel` working.
    if "test" in sys.argv[1:2]:
        multiprocessing.set_start_method("fork", force=True)
    main()
