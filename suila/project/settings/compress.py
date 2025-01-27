# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

COMPRESS_PRECOMPILERS = (("text/x-scss", "django_libsass.SassCompiler"),)
COMPRESS_REBUILD_TIMEOUT = 0
COMPRESS_ENABLED = True
LIBSASS_OUTPUT_STYLE = "compressed"
