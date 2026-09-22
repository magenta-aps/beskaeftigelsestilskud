# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal

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


class UpdateBenefitTransferredTest(MigratorTestCase):
    migrate_from = (
        "suila",
        "0040_prismepostingstatusfile_and_more",
    )
    migrate_to = ("suila", "0041_update_benefit_transferred_after_manual_override")

    def prepare(self):

        Year = self.old_state.apps.get_model("suila", "Year")
        Person = self.old_state.apps.get_model("suila", "Person")
        PersonYear = self.old_state.apps.get_model("suila", "PersonYear")
        PersonMonth = self.old_state.apps.get_model("suila", "PersonMonth")
        PrismeBatch = self.old_state.apps.get_model("suila", "PrismeBatch")
        PrismeBatchItem = self.old_state.apps.get_model("suila", "PrismeBatchItem")

        self.year = Year.objects.create(year=2025)
        self.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")

        self.person_year = PersonYear.objects.create(
            person=self.person,
            year=self.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        # This person has benefit_calculated == 0. Meaning that we put it to zero
        # manually because the person did not receive benefit. For some reason.
        self.person_month = PersonMonth.objects.create(
            person_year=self.person_year,
            month=1,
            import_date=date.today(),
            benefit_transferred=317,
            benefit_calculated=0,
        )
        self.prisme_batch = PrismeBatch.objects.create(
            status="sent", export_date=date.today(), prefix=1
        )

        self.prisme_item = PrismeBatchItem.objects.create(
            person_month=self.person_month,
            prisme_batch=self.prisme_batch,
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800000031700&"  # 317 kr.
                "09+&1002&1100000101001111&1220250414&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )

    def test_migration(self):
        person_month = self.new_state.apps.get_model(
            "suila", "PersonMonth"
        ).objects.get(month=1)

        self.assertEqual(person_month.benefit_transferred, 0)


class ForeignPensionIncomeMigrationMixin:
    """Sets up income reports for two person months:

    - `self.person_month1` has a report with foreign pension (plus a second report
      without, belonging to another employer)
    - `self.person_month2` has a single report without foreign pension

    `a_income` and `amount_sum` are written explicitly, since the model methods that
    normally maintain them are not available on the historical models.
    """

    def create_income_data(self, apps, a_income, amount_sum):
        Year = apps.get_model("suila", "Year")
        Person = apps.get_model("suila", "Person")
        PersonYear = apps.get_model("suila", "PersonYear")
        PersonMonth = apps.get_model("suila", "PersonMonth")
        Employer = apps.get_model("suila", "Employer")
        MonthlyIncomeReport = apps.get_model("suila", "MonthlyIncomeReport")

        year = Year.objects.create(year=2026)
        person = Person.objects.create(name="Jens Hansen", cpr="1234567890")
        person_year = PersonYear.objects.create(
            person=person,
            year=year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )

        def create_person_month(month, amount_sum):
            return PersonMonth.objects.create(
                person_year=person_year,
                month=month,
                import_date=date.today(),
                amount_sum=amount_sum,
            )

        def create_report(person_month, employer, a_income, **kwargs):
            return MonthlyIncomeReport.objects.create(
                person_month=person_month,
                employer=employer,
                month=person_month.month,
                year=person_month.person_year.year_id,
                a_income=a_income,
                **kwargs,
            )

        employer1 = Employer.objects.create(cvr=12345678)
        employer2 = Employer.objects.create(cvr=87654321)

        # A person month where one of the two reports has foreign pension. Its
        # `amount_sum` covers both reports, and includes U income.
        self.person_month1 = create_person_month(1, amount_sum)
        create_report(
            self.person_month1,
            employer1,
            a_income,
            salary_income=Decimal("15000.00"),
            employer_paid_gl_pension_income=Decimal("100.00"),
            catchsale_income=Decimal("400.00"),
            foreign_pension_income=Decimal("5000.00"),
            u_income=Decimal("1000.00"),
        )
        create_report(
            self.person_month1,
            employer2,
            Decimal("1000.00"),
            salary_income=Decimal("1000.00"),
        )

        # A person month without foreign pension. Its `a_income` and `amount_sum` are
        # deliberately inconsistent with the income fields, so that the test can tell
        # whether the migration touched them.
        self.person_month2 = create_person_month(2, Decimal("99.00"))
        create_report(
            self.person_month2,
            employer1,
            Decimal("99.00"),
            salary_income=Decimal("8000.00"),
        )

    def get_report(self, month, cvr):
        return self.new_state.apps.get_model(
            "suila", "MonthlyIncomeReport"
        ).objects.get(person_month__month=month, employer__cvr=cvr)

    def get_person_month(self, month):
        return self.new_state.apps.get_model("suila", "PersonMonth").objects.get(
            month=month
        )


class AddForeignPensionToAIncomeTest(
    ForeignPensionIncomeMigrationMixin, MigratorTestCase
):
    migrate_from = ("suila", "0068_suilaeboksmessage_person_year_and_more")
    migrate_to = ("suila", "0069_recalculate_a_income_with_foreign_pension")

    def prepare(self):
        # `a_income` and `amount_sum` as they were calculated before foreign pension
        # became part of the A income: 15000 + 100 + 400 = 15500, and
        # 15500 + 1000 (other report) + 1000 (U income) = 17500.
        self.create_income_data(
            self.old_state.apps,
            a_income=Decimal("15500.00"),
            amount_sum=Decimal("17500.00"),
        )

    def test_foreign_pension_is_added_to_a_income(self):
        self.assertEqual(
            self.get_report(1, 12345678).a_income,
            Decimal("20500.00"),  # 15.500 + 5.000 = 20.500
        )

    def test_amount_sum_is_updated(self):
        self.assertEqual(
            self.get_person_month(1).amount_sum,
            Decimal("22500.00"),  # 17500 + 5000 = 22500
        )

    def test_reports_without_foreign_pension_are_untouched(self):
        # The report belonging to the same person month as the recalculated one
        self.assertEqual(self.get_report(1, 87654321).a_income, Decimal("1000.00"))
        # ... and a person month with no foreign pension at all
        self.assertEqual(self.get_report(2, 12345678).a_income, Decimal("99.00"))
        self.assertEqual(self.get_person_month(2).amount_sum, Decimal("99.00"))


class RemoveForeignPensionFromAIncomeTest(
    ForeignPensionIncomeMigrationMixin, MigratorTestCase
):
    """The migration is reversible, so that the change can be rolled back together
    with the code that introduced it.
    """

    migrate_from = ("suila", "0069_recalculate_a_income_with_foreign_pension")
    migrate_to = ("suila", "0068_suilaeboksmessage_person_year_and_more")

    def prepare(self):
        self.create_income_data(
            self.old_state.apps,
            a_income=Decimal("20500.00"),
            amount_sum=Decimal("22500.00"),
        )

    def test_foreign_pension_is_removed_from_a_income(self):
        self.assertEqual(
            self.get_report(1, 12345678).a_income,
            Decimal("15500.00"),  # 20.500 - 5.000 = 15.500
        )

    def test_amount_sum_is_updated(self):
        self.assertEqual(
            self.get_person_month(1).amount_sum,
            Decimal("17500.00"),  # 22500 - 5000 = 17500
        )


class AddAmountToPrismeBatchItemTest(MigratorTestCase):
    migrate_from = ("suila", "0070_finalsettlement_invoice_id_and_more")
    migrate_to = ("suila", "0071_historicalperson_benefit_difference_and_more")

    def prepare(self):
        Year = self.old_state.apps.get_model("suila", "Year")
        Person = self.old_state.apps.get_model("suila", "Person")
        PersonYear = self.old_state.apps.get_model("suila", "PersonYear")
        PersonMonth = self.old_state.apps.get_model("suila", "PersonMonth")
        PrismeBatch = self.old_state.apps.get_model("suila", "PrismeBatch")
        PrismeBatchItem = self.old_state.apps.get_model("suila", "PrismeBatchItem")
        FinalSettlement = self.old_state.apps.get_model("suila", "FinalSettlement")
        AnnualIncome = self.old_state.apps.get_model("suila", "AnnualIncome")

        self.year = Year.objects.create(year=2025)
        self.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")

        self.person_year = PersonYear.objects.create(
            person=self.person,
            year=self.year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        # Create personmonth with 2.600kr. benefit transferred.
        self.person_month = PersonMonth.objects.create(
            person_year=self.person_year,
            month=1,
            import_date=date.today(),
            benefit_transferred=2600,
            benefit_calculated=0,
        )
        # Create annualIncome of 300.000kr., leading to 12.600kr. total benefit
        self.annual_income = AnnualIncome.objects.create(
            person_year=self.person_year,
            salary=Decimal("300_000"),
        )
        # Final settlement will have result 12.600kr. - 2.600kr. = 10.000kr.
        self.final_settlement = FinalSettlement.objects.create(
            annual_income=self.annual_income,
            _result=Decimal("10_000"),
        )
        self.prisme_batch = PrismeBatch.objects.create(
            status="sent", export_date=date.today(), prefix=1
        )

        self.prisme_item_person_month = PrismeBatchItem.objects.create(
            person_month=self.person_month,
            prisme_batch=self.prisme_batch,
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800000260000&"  # 2600 kr.
                "09+&1002&1100000101001111&1220250414&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )
        self.prisme_item_final_settlement = PrismeBatchItem.objects.create(
            final_settlement=self.final_settlement,
            prisme_batch=self.prisme_batch,
            g68_content=(
                "000G6800004011&020900&0300&"
                "07000000000000000000&0800001000000&"  # 10.000 kr.
                "09+&1002&1100000101001111&1220250414&"
                "16202504080080400004&"
                "1700000000000027100004&40www.suila.gl takuuk"
            ),
        )

    def test_migration(self):
        prisme_item_person_month = self.new_state.apps.get_model(
            "suila", "PersonMonth"
        ).objects.get(month=1).prismebatchitem
        prisme_item_final_settlement = self.new_state.apps.get_model(
            "suila", "FinalSettlement"
        ).objects.first().prismebatchitem

        self.assertEqual(prisme_item_final_settlement._amount, Decimal("10_000"))
        self.assertIsNone(prisme_item_person_month._amount)
