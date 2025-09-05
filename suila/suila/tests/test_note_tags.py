# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.test import SimpleTestCase
from django.utils.translation import override

from suila.templatetags.note_tags import translate_note


class TestFormatCpr(SimpleTestCase):

    def test_translate_pause_note(self):

        note = (
            "Starter udbetalingspause\n"
            "Borger må ikke genoptage udbetalinger\n"
            "Indikation af systemfejl\n"
            "Eboks besked sendt til borger\n"
            "<note>"
        )

        with override("en"):
            self.assertEqual(
                translate_note(note),
                (
                    "Starting payment pause\n"
                    "Citizen may not resume payments\n"
                    "Indication of system error\n"
                    "Eboks message sent to citizen\n"
                    "<note>"
                ),
            )

    def test_translate_override_income_note(self):

        note = "Benyt manuelt estimeret årsindkomst\n(1,234 kr.)\n<note>"

        with override("en"):
            self.assertEqual(
                translate_note(note),
                ("Use manually estimated annual income\n(1,234 kr.)\n<note>"),
            )

    def test_translate_change_engine_note(self):

        note = (
            "A-indkomst estimeringsmotor ændret:\n"
            "InYearExtrapolationEngine -> TwelveMonthsSummationEngine\n"
            "U-indkomst estimeringsmotor ændret:\n"
            "TwelveMonthsSummationEngine -> MonthlyContinuationEngine"
            "<note>"
        )

        with override("en"):
            self.assertEqual(
                translate_note(note),
                (
                    "A-income estimation engine changed:\n"
                    "InYearExtrapolationEngine -> TwelveMonthsSummationEngine\n"
                    "U-income estimation engine changed:\n"
                    "TwelveMonthsSummationEngine -> MonthlyContinuationEngine"
                    "<note>"
                ),
            )
