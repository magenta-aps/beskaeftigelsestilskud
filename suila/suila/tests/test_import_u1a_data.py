# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import ANY, MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.forms import model_to_dict
from django.test import TestCase

from suila.integrations.akap.u1a import AKAPU1A, AKAPU1AItem
from suila.management.commands.import_u1a_data import Command as ImportU1ADataCommand
from suila.models import (
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)


class TestImportU1ADataCommand(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.command = ImportU1ADataCommand()
        self.command.stdout = StringIO()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year, _ = Year.objects.get_or_create(year=2025)

        cls.person1 = Person.objects.create(
            name="Jens Hansen-1",
            cpr="1234567890",
        )

        cls.u1a_1 = AKAPU1A(
            id=1,
            navn="Test U1A",
            revisionsfirma="Test Reivisions Firma",
            virksomhedsnavn="Test virksomhed",
            cvr="12345678",
            email="test@example.com",
            regnskabsår=cls.year.year,
            u1_udfyldt=False,
            udbytte=Decimal("1337.0"),
            by="Aarhus",
            dato=datetime.now().date(),
            dato_vedtagelse=datetime.now().date() + timedelta(days=1),
            underskriftsberettiget="Test Berettiget",
            oprettet=datetime.now() - timedelta(days=7),
            oprettet_af_cpr=cls.person1.cpr,
        )

    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items")
    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items_unique_cprs")
    def test_akap_fetch_method_usage(
        self,
        mock_get_akap_u1a_items_unique_cprs: MagicMock,
        mock_get_akap_u1a_items: MagicMock,
    ):
        mock_get_akap_u1a_items_unique_cprs.return_value = [self.person1.cpr]

        call_command(self.command)

        mock_get_akap_u1a_items_unique_cprs.assert_called_once_with(
            settings.AKAP_HOST, settings.AKAP_API_SECRET, self.year.year, fetch_all=True
        )
        mock_get_akap_u1a_items.assert_called_once_with(
            settings.AKAP_HOST,
            settings.AKAP_API_SECRET,
            year=self.year.year,
            cpr=self.person1.cpr,
            fetch_all=True,
        )

    # TODO: Make tests which verify the logic which handles the fetched U1A items
    # and creates MonthlyIncomeReports + updates PersonMonth sums

    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items")
    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items_unique_cprs")
    def test_model_creations(
        self,
        mock_get_akap_u1a_items_unique_cprs: MagicMock,
        mock_get_akap_u1a_items: MagicMock,
    ):
        # Mocking
        mock_get_akap_u1a_items_unique_cprs.return_value = [self.person1.cpr]
        mock_get_akap_u1a_items.return_value = [
            AKAPU1AItem(
                id=1,
                u1a=self.u1a_1,
                cpr_cvr_tin="1234567891",
                navn="Test Person",
                adresse="Testvej 1337",
                postnummer="8000",
                by="Aarhus",
                land="Danmark",
                udbytte=Decimal("1337.00"),
                oprettet=datetime.now(),
            )
        ]

        # Invoke
        call_command(self.command)

        # Assert fetch mocking methods was called
        mock_get_akap_u1a_items_unique_cprs.assert_called_once_with(
            settings.AKAP_HOST, settings.AKAP_API_SECRET, self.year.year, fetch_all=True
        )
        mock_get_akap_u1a_items.assert_called_once_with(
            settings.AKAP_HOST,
            settings.AKAP_API_SECRET,
            year=self.year.year,
            cpr=self.person1.cpr,
            fetch_all=True,
        )

        # Assert PersonYear creation
        person_year = PersonYear.objects.get(person=self.person1, year=self.year)
        self.assertEqual(
            model_to_dict(person_year),
            {
                "id": ANY,
                "load": ANY,
                "b_expenses": Decimal("0.00"),
                "b_income": Decimal("0.00"),
                "catchsale_expenses": Decimal("0.00"),
                "person": self.person1.id,
                "preferred_estimation_engine_a": "InYearExtrapolationEngine",
                "preferred_estimation_engine_u": "InYearExtrapolationEngine",
                "stability_score_a": None,
                "stability_score_b": None,
                "tax_scope": "FULD",
                "year": self.year.year,
            },
        )

        # Assert Employer creation
        employer = Employer.objects.get(cvr=self.u1a_1.cvr)
        self.assertEqual(
            model_to_dict(employer),
            {
                "cvr": int(self.u1a_1.cvr),
                "id": ANY,
                "load": ANY,
                "name": self.u1a_1.virksomhedsnavn,
            },
        )

        # Assert PersonMonth creation
        person_month = PersonMonth.objects.get(
            person_year=person_year, month=self.u1a_1.dato_vedtagelse.month
        )

        self.assertEqual(
            model_to_dict(person_month),
            {
                "id": ANY,
                "load": ANY,
                "import_date": ANY,
                "actual_year_benefit": None,
                "amount_sum": Decimal("1337.00"),
                "benefit_paid": None,
                "estimated_year_benefit": None,
                "estimated_year_result": None,
                "fully_tax_liable": None,
                "has_paid_b_tax": False,
                "month": self.u1a_1.dato_vedtagelse.month,
                "municipality_code": None,
                "municipality_name": None,
                "person_year": person_year.id,
                "prior_benefit_paid": None,
            },
        )

        # Assert MonthlyIncomeReport's
        monthly_income_reports = MonthlyIncomeReport.objects.filter(
            employer=employer,
            person_month=person_month,
            u_income__gt=Decimal(0),
        )

        self.assertEqual(
            [model_to_dict(model) for model in monthly_income_reports],
            [
                {
                    "id": ANY,
                    "load": ANY,
                    "employer": employer.id,
                    "person_month": person_month.id,
                    "year": person_year.year.year,
                    "month": person_month.month,
                    "a_income": Decimal("0.00"),
                    "u_income": Decimal("1337.00"),
                    "alimony_income": Decimal("0.00"),
                    "capital_income": Decimal("0.00"),
                    "catchsale_income": Decimal("0.00"),
                    "civil_servant_pension_income": Decimal("0.00"),
                    "dis_gis_income": Decimal("0.00"),
                    "disability_pension_income": Decimal("0.00"),
                    "employer_paid_gl_pension_income": Decimal("0.00"),
                    "foreign_pension_income": Decimal("0.00"),
                    "ignored_benefits_income": Decimal("0.00"),
                    "other_pension_income": Decimal("0.00"),
                    "public_assistance_income": Decimal("0.00"),
                    "retirement_pension_income": Decimal("0.00"),
                    "salary_income": Decimal("0.00"),
                }
            ],
        )

    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items")
    @patch("suila.management.commands.import_u1a_data.get_akap_u1a_items_unique_cprs")
    def test_modal_updates(
        self,
        mock_get_akap_u1a_items_unique_cprs: MagicMock,
        mock_get_akap_u1a_items: MagicMock,
    ):
        # Test specific data
        existing_person_year = PersonYear.objects.create(
            person=self.person1,
            year=self.year,
        )

        existing_person_month = PersonMonth.objects.create(
            person_year=existing_person_year,
            month=self.u1a_1.dato_vedtagelse.month,
            import_date=datetime.now().date(),
        )

        u1a_employer = Employer.objects.create(
            cvr=self.u1a_1.cvr,
            name=self.u1a_1.virksomhedsnavn,
        )

        existing_monthly_income_report = MonthlyIncomeReport.objects.create(
            employer=u1a_employer,
            person_month=existing_person_month,
            salary_income=Decimal("1234.00"),
        )

        # Mocking
        mock_get_akap_u1a_items_unique_cprs.return_value = [self.person1.cpr]
        mock_get_akap_u1a_items.return_value = [
            AKAPU1AItem(
                id=1,
                u1a=self.u1a_1,
                cpr_cvr_tin="1234567891",
                navn="Test Person",
                adresse="Testvej 1337",
                postnummer="8000",
                by="Aarhus",
                land="Danmark",
                udbytte=Decimal("1337.00"),
                oprettet=datetime.now(),
            )
        ]

        # Invoke
        call_command(self.command)

        # Asserts MonthlyIncomeReport got updated correctly
        updated_monthly_income_reports = MonthlyIncomeReport.objects.get(
            pk=existing_monthly_income_report.id
        )
        self.assertEqual(
            model_to_dict(updated_monthly_income_reports),
            {
                "id": ANY,
                "load": ANY,
                "employer": u1a_employer.id,
                "person_month": existing_person_month.id,
                "year": existing_person_year.year.year,
                "month": existing_person_month.month,
                "a_income": Decimal("1234.00"),
                "u_income": Decimal("1337.00"),
                "alimony_income": Decimal("0.00"),
                "capital_income": Decimal("0.00"),
                "catchsale_income": Decimal("0.00"),
                "civil_servant_pension_income": Decimal("0.00"),
                "dis_gis_income": Decimal("0.00"),
                "disability_pension_income": Decimal("0.00"),
                "employer_paid_gl_pension_income": Decimal("0.00"),
                "foreign_pension_income": Decimal("0.00"),
                "ignored_benefits_income": Decimal("0.00"),
                "other_pension_income": Decimal("0.00"),
                "public_assistance_income": Decimal("0.00"),
                "retirement_pension_income": Decimal("0.00"),
                "salary_income": Decimal("1234.00"),
            },
        )

        # Assert PersonMonth.amount_sum changes
        updated_person_month = PersonMonth.objects.get(pk=existing_person_month.id)
        self.assertEqual(
            model_to_dict(updated_person_month),
            {
                "id": updated_person_month.id,
                "person_year": existing_person_year.id,
                "month": existing_person_month.month,
                "load": ANY,
                "import_date": ANY,
                "actual_year_benefit": None,
                "amount_sum": Decimal("2571.00"),
                "benefit_paid": None,
                "estimated_year_benefit": None,
                "estimated_year_result": None,
                "fully_tax_liable": None,
                "has_paid_b_tax": False,
                "municipality_code": None,
                "municipality_name": None,
                "prior_benefit_paid": None,
            },
        )
