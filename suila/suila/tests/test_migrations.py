# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date

from django_test_migrations.contrib.unittest_case import MigratorTestCase


class PopulateBenefitTransferredTest(MigratorTestCase):

    migrate_from = (
        "suila",
        "0037_remove_historicalpersonmonth_prior_benefit_calculated_and_more",
    )
    migrate_to = ("suila", "0038_populate_benefit_transferred")

    def prepare(self):

        Year = self.old_state.apps.get_model("suila", "Year")
        Person = self.old_state.apps.get_model("suila", "Person")
        PersonYear = self.old_state.apps.get_model("suila", "PersonYear")
        PersonMonth = self.old_state.apps.get_model("suila", "PersonMonth")
        PrismeBatch = self.old_state.apps.get_model("suila", "PrismeBatch")
        PrismeBatchItem = self.old_state.apps.get_model("suila", "PrismeBatchItem")

        self.year = Year.objects.create(year=2025)
        self.last_year = Year.objects.create(year=2024)

        # A person with 2 payouts. One in January and one in February.
        self.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")

        # A person without payouts
        self.person2 = Person.objects.create(name="Jakob Hansen", cpr="1234567891")

        for year in [self.year, self.last_year]:

            self.person_year = PersonYear.objects.create(
                person=self.person,
                year=year,
                preferred_estimation_engine_a="InYearExtrapolationEngine",
            )

            self.person_month1 = PersonMonth.objects.create(
                person_year=self.person_year, month=1, import_date=date.today()
            )
            self.person_month2 = PersonMonth.objects.create(
                person_year=self.person_year, month=2, import_date=date.today()
            )
            self.person_month3 = PersonMonth.objects.create(
                person_year=self.person_year, month=3, import_date=date.today()
            )

            self.prisme_batch = PrismeBatch.objects.create(
                status="sent", export_date=date.today(), prefix=1
            )

            # Month 1 has a prisme-batch item
            self.prisme_item1 = PrismeBatchItem.objects.create(
                person_month=self.person_month1,
                prisme_batch=self.prisme_batch,
                g68_content=(
                    "000G6800004011&020900&0300&"
                    "07000000000000000000&0800000031700&"  # 317 kr.
                    "09+&1002&1100000101001111&1220250414&"
                    "16202504080080400004&"
                    "1700000000000027100004&40www.suila.gl takuuk"
                ),
            )

            # Month 2 does not have a prisme-batch item
            self.prisme_item2 = PrismeBatchItem.objects.create(
                person_month=self.person_month2,
                prisme_batch=self.prisme_batch,
                g68_content=(
                    "000G6800004011&020900&0300&"
                    "07000000000000000000&0800000031800&"  # 318 kr.
                    "09+&1002&1100000101001111&1220250414&"
                    "16202504080080400004&"
                    "1700000000000027100004&40www.suila.gl takuuk"
                ),
            )

            self.person_year2 = PersonYear.objects.create(
                person=self.person2,
                year=year,
                preferred_estimation_engine_a="InYearExtrapolationEngine",
            )

            PersonMonth.objects.create(
                person_year=self.person_year2, month=1, import_date=date.today()
            )
            PersonMonth.objects.create(
                person_year=self.person_year2, month=2, import_date=date.today()
            )
            PersonMonth.objects.create(
                person_year=self.person_year2, month=3, import_date=date.today()
            )

    def get_person_month(self, month, name, year=2025):
        return self.new_state.apps.get_model("suila", "PersonMonth").objects.get(
            month=month, person_year__person__name=name, person_year__year__year=year
        )

    def test_migration(self):
        person_month1 = self.get_person_month(1, "Jens Hansen")
        person_month2 = self.get_person_month(2, "Jens Hansen")
        person_month3 = self.get_person_month(3, "Jens Hansen")

        self.assertEqual(person_month1.benefit_transferred, 317)
        self.assertEqual(person_month2.benefit_transferred, 318)
        self.assertEqual(person_month3.benefit_transferred, 0)
        self.assertEqual(person_month1.prior_benefit_transferred, None)
        self.assertEqual(person_month2.prior_benefit_transferred, 317)
        self.assertEqual(person_month3.prior_benefit_transferred, 317 + 318)

    def test_migration_no_prisme_batch_items(self):
        person_month1 = self.get_person_month(1, "Jakob Hansen")
        person_month2 = self.get_person_month(2, "Jakob Hansen")
        person_month3 = self.get_person_month(3, "Jakob Hansen")

        self.assertEqual(person_month1.benefit_transferred, 0)
        self.assertEqual(person_month2.benefit_transferred, 0)
        self.assertEqual(person_month3.benefit_transferred, 0)
        self.assertEqual(person_month1.prior_benefit_transferred, None)
        self.assertEqual(person_month2.prior_benefit_transferred, None)
        self.assertEqual(person_month3.prior_benefit_transferred, None)

    def test_that_previous_years_are_not_processed(self):
        person_month1 = self.get_person_month(1, "Jens Hansen", 2024)
        person_month2 = self.get_person_month(2, "Jens Hansen", 2024)
        person_month3 = self.get_person_month(3, "Jens Hansen", 2024)

        self.assertEqual(person_month1.benefit_transferred, 0)
        self.assertEqual(person_month2.benefit_transferred, 0)
        self.assertEqual(person_month3.benefit_transferred, 0)
        self.assertEqual(person_month1.prior_benefit_transferred, None)
        self.assertEqual(person_month2.prior_benefit_transferred, None)
        self.assertEqual(person_month3.prior_benefit_transferred, None)
