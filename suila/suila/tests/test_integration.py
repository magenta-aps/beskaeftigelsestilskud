# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import calendar
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.files.temp import NamedTemporaryFile
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from requests.models import Response
from tenQ.writer.g68 import G68Transaction, Udbetalingsbeløb

from suila.models import (
    PersonMonth,
    PersonYear,
    StandardWorkBenefitCalculationMethod,
    TaxInformationPeriod,
    Year,
)


def get_days_in_month(year, month):
    # calendar.monthrange returns (weekday_of_first_day, number_of_days_in_month)
    _, num_days = calendar.monthrange(year, month)
    return list(range(1, num_days + 1))


class PrismeMocks:

    def setUp(self):
        super().setUp()

        self.prisme_patcher = patch(
            "suila.integrations.prisme.benefits.put_file_in_prisme_folder"
        )

        self.get_file_patcher = patch(
            "suila.integrations.prisme.sftp_import.get_file_in_prisme_folder"
        )

        self.list_prisme_folder_patcher = patch(
            "suila.integrations.prisme.sftp_import.list_prisme_folder"
        )

        self.prisme_mock = self.prisme_patcher.start()
        self.get_file_in_prisme_folder_mock = self.get_file_patcher.start()
        self.list_prisme_folder_mock = self.list_prisme_folder_patcher.start()

        self.addCleanup(self.prisme_patcher.stop)
        self.addCleanup(self.get_file_in_prisme_folder_mock.stop)
        self.addCleanup(self.list_prisme_folder_mock.stop)

    def generate_btax_files(self, month, year):
        btax_file_content = (
            "BTAX;"
            f"{self.cpr};"
            ";"
            f"{self.year};"
            "-3439;"
            "2000004544;"
            "3439;"
            f"{self.year}/{str(month).zfill(2)}/20;"
            f"{str(month).zfill(3)}"
        )

        btax_files = [f"BSKAT_2022_207022_27-{month}-{year}_120035.csv"]
        self.list_prisme_folder_mock.return_value = btax_files

        self.get_file_in_prisme_folder_mock.side_effect = [
            BytesIO(btax_file_content.encode("utf-16-le"))
        ]


class EskatMocks:

    def setUp(self):
        super().setUp()

        self.taxinformation_json_data = {
            "data": [],
            "message": (
                "https://eskatdrift/eTaxCommonDataApi/api/"
                "taxinformation/get/chunks/all/2025"
            ),
            "chunk": 1,
            "chunkSize": 0,
            "totalChunks": 1,
            "totalRecordsInChunks": 0,
        }

        self.monthlyincome_json_data = {
            "data": [],
            "message": "string",
            "chunk": 1,
            "chunkSize": 0,
            "totalChunks": 1,
            "totalRecordsInChunks": 0,
        }

        self.annualincome_json_data = {
            "data": [],
            "message": "string",
            "chunk": 1,
            "chunkSize": 0,
            "totalChunks": 1,
            "totalRecordsInChunks": 0,
        }

        self.expectedincome_json_data = {
            "data": [],
            "message": "string",
            "chunk": 1,
            "chunkSize": 0,
            "totalChunks": 1,
            "totalRecordsInChunks": 0,
        }

        self.eskat_session_patcher = patch(
            "suila.integrations.eskat.client.requests.Session"
        )
        MockEskatSessionClass = self.eskat_session_patcher.start()
        self.addCleanup(MockEskatSessionClass.stop)

        # The instance returned when get_session() calls Session()
        mock_eskat_session_instance = MockEskatSessionClass.return_value

        def eskat_response_mocker(url, *args, **kwargs):

            response_mock = MagicMock(spec=Response)

            if "taxinformation" in url:
                response_mock.json.return_value = self.taxinformation_json_data
            elif "monthlyincome" in url:
                response_mock.json.return_value = self.monthlyincome_json_data
            elif "expectedincome" in url:
                response_mock.json.return_value = self.expectedincome_json_data
            elif "annualincome" in url:
                response_mock.json.return_value = self.annualincome_json_data

            response_mock.status_code = 200
            return response_mock

        mock_eskat_session_instance.get.side_effect = eskat_response_mocker

    def _get_datetime(self, month: int, day: int):
        return datetime(
            self.year, month, day, tzinfo=timezone.get_current_timezone()
        ).strftime("%Y-%m-%dT%H:%M:%S")

    def add_expectedincome_record(self, cpr, b_income=0):
        self.expectedincome_json_data["data"] += [
            {
                "cpr": cpr,
                "year": self.year,
                "valid_from": f"{self.year}-01-01T00:00:00",
                "do_expect_a_income": True,
                "capital_income": b_income,
                "education_support_income": 0,
                "care_fee_income": 0.0,
                "alimony_income": 0.0,
                "benefits_income": 0.0,
                "other_b_income": 0.0,
                "gross_business_income": 0.0,
                "catch_sale_factory_income": 0.0,
                "catch_sale_market_income": 0.0,
            }
        ]
        self.expectedincome_json_data["chunkSize"] += 1
        self.expectedincome_json_data["totalRecordsInChunks"] += 1

    def add_taxinformation_record(self, cpr, tax_scope, start_date, end_date):
        self.taxinformation_json_data["data"] += [
            {
                "cpr": cpr,
                "year": self.year,
                "taxScope": tax_scope,
                "startDate": self._get_datetime(start_date[0], start_date[1]),
                "endDate": self._get_datetime(end_date[0], end_date[1]),
                "catchSalePct": None,
                "taxMunicipalityNumber": "32",
                "cprMunicipalityCode": self.location_code,
                "regionNumber": None,
                "regionName": "",
                "districtName": "Nuuk",
            }
        ]
        self.taxinformation_json_data["chunkSize"] += 1
        self.taxinformation_json_data["totalRecordsInChunks"] += 1

    def add_monthlyincome_record(self, cpr, month, income=0):
        self.monthlyincome_json_data["data"] += [
            {
                "cpr": cpr,
                "cvr": "567",
                "year": self.year,
                "month": month,
                "salaryIncome": income,
                "catchsaleIncome": 0,
                "publicAssistanceIncome": 0,
                "alimonyIncome": 0,
                "disGisIncome": 0,
                "retirementPensionIncome": 0,
                "disabilityPensionIncome": 0,
                "ignoredBenefitsIncome": 0,
                "employerPaidGLPensionIncome": 0,
                "foreignPensionIncome": 0,
                "civilServantPensionIncome": 0,
                "otherPensionIncome": 0,
            }
        ]

        self.monthlyincome_json_data["chunkSize"] += 1
        self.monthlyincome_json_data["totalRecordsInChunks"] += 1

    def add_annualincome_record(self, cpr, salary=0):
        self.annualincome_json_data["data"] += [
            {
                "cpr": cpr,
                "year": self.year,
                "salary": salary,
                "public_assistance_income": None,
                "retirement_pension_income": None,
                "disability_pension_income": None,
                "ignored_benefits": None,
                "occupational_benefit": None,
                "foreign_pension_income": None,
                "subsidy_foreign_pension_income": None,
                "dis_gis_income": None,
                "other_a_income": None,
                "deposit_interest_income": None,
                "bond_interest_income": None,
                "other_interest_income": None,
                "education_support_income": None,
                "care_fee_income": None,
                "alimony_income": None,
                "foreign_dividend_income": None,
                "foreign_income": None,
                "free_journey_income": None,
                "group_life_income": None,
                "rental_income": None,
                "other_b_income": None,
                "free_board_income": None,
                "free_lodging_income": None,
                "free_housing_income": None,
                "free_phone_income": None,
                "free_car_income": None,
                "free_internet_income": None,
                "free_boat_income": None,
                "free_other_income": None,
                "pension_payment_income": None,
                "catch_sale_market_income": None,
                "catch_sale_factory_income": None,
                "account_tax_result": None,
                "account_share_business_amount": None,
                "shareholder_dividend_income": None,
            }
        ]
        self.annualincome_json_data["chunkSize"] += 1
        self.annualincome_json_data["totalRecordsInChunks"] += 1


class U1AMocks:
    def setUp(self):
        super().setUp()

        self.list_u1a_response = {
            "items": [],
            "count": 0,
        }

        self.u1a_item_response = {
            "items": [],
            "count": 0,
        }

        self.u1a_unique_cpr_response = {
            "items": [],
            "count": 0,
        }

        def u1a_response_mocker(url, *args, **kwargs):

            response_mock = MagicMock(spec=Response)

            if "u1a-items/unique/cprs" in url:
                response_mock.json.return_value = self.u1a_unique_cpr_response
            elif "u1a-items" in url:
                response_mock.json.return_value = self.u1a_item_response
            elif "u1a" in url:
                response_mock.json.return_value = self.list_u1a_response

            response_mock.status_code = 200
            return response_mock

        self.get_u1a_patcher = patch("suila.integrations.akap.u1a.requests")
        get_u1a_mock = self.get_u1a_patcher.start()
        self.addCleanup(get_u1a_mock.stop)

        get_u1a_mock.get.side_effect = u1a_response_mocker

    def add_u1a_record(self, cpr, udbytte=0):
        # Create AKAPU1A dict with proper types
        item = {
            "id": 1,
            "navn": "Test U1A",
            "revisionsfirma": "Test Reivisions Firma",
            "virksomhedsnavn": "Test virksomhed",
            "cvr": "12345678",
            "email": "test@example.com",
            "regnskabsår": self.year,
            "u1_udfyldt": False,
            "udbytte": Decimal(udbytte),
            "by": "Aarhus",
            "dato": date.fromisoformat("2025-09-23"),
            "dato_vedtagelse": date.fromisoformat("2025-09-24"),
            "underskriftsberettiget": "Test Berettiget",
            "oprettet": datetime.fromisoformat("2025-09-16T12:00:00"),
            "oprettet_af_cpr": cpr,
        }

        # Append to list of U1A items
        self.list_u1a_response["items"].append(item)
        self.list_u1a_response["count"] += 1

        # Create AKAPU1AItem dict with proper types
        u1a_item = {
            "id": 1,
            "u1a": item,
            "cpr_cvr_tin": cpr,
            "navn": "Test Person",
            "adresse": "Testvej 1337",
            "postnummer": "8000",
            "by": "Aarhus",
            "land": "Danmark",
            "udbytte": Decimal(udbytte),
            "oprettet": datetime.fromisoformat("2025-09-23T12:00:00"),
        }

        self.u1a_item_response["items"].append(u1a_item)
        self.u1a_item_response["count"] += 1

        # Keep track of unique CPRs
        self.u1a_unique_cpr_response["items"].append(cpr)
        self.u1a_unique_cpr_response["count"] += 1


class DafoMocks:
    def setUp(self):
        super().setUp()

        self.person_info_response = {
            "civilstand": None,
            "fornavn": "Henry",
            "efternavn": "Cavill",
            "adresse": "Silkeborgvej 260",
            "bynavn": "Åbyhøj",
            "postnummer": "8230",
            "udlandsadresse": None,
            "landekode": "DK",
            "statuskode": 1,
        }

        self.company_info_response = {
            "source": "CVR",
            "cvrNummer": "11221122",
            "navn": "Firmanavn ApS",
            "forretningsområde": "Forretningsområdenavn",
            "statuskode": "NORMAL",
            "statuskodedato": "2000-01-01",
            "myndighedskode": 960,
            "kommune": "Kommunenavn",
            "vejkode": 100,
            "stedkode": 1000,
            "adresse": "Testvej 123, 1. sal",
            "postboks": 101,
            "postnummer": 9999,
            "bynavn": "Testby",
            "landekode": "GL",
            "email": "company@example.org",
            "telefon": "123456",
        }

        self.dafo_subscription_response = {
            "path": None,
            "terms": "https://doc.test.data.gl/terms",
            "requestTimestamp": None,
            "responseTimestamp": None,
            "newestResultTimestamp": "2025-09-09T16:01:00Z",
            "username": None,
            "page": 0,
            "pageSize": 100,
            "results": [self.cpr],
        }

        self.pitu_session_patcher = patch("suila.integrations.pitu.client.Session")
        MockPituSessionClass = self.pitu_session_patcher.start()
        self.addCleanup(MockPituSessionClass.stop)

        # The instance returned when get_session() calls Session()
        mock_pitu_session_instance = MockPituSessionClass.return_value

        def dafo_response_mocker(url, *args, **kwargs):
            route = url.split("/")[-1]
            response_mock = MagicMock(spec=Response)
            if route == "fetchEvents":
                response_mock.json.return_value = self.dafo_subscription_response
            elif len(route) == 8:  # cvr number
                response_mock.json.return_value = self.company_info_response
            elif len(route) == 10:  # cpr number
                response_mock.json.return_value = self.person_info_response

            response_mock.status_code = 200
            return response_mock

        mock_pitu_session_instance.get.side_effect = dafo_response_mocker


client_cert_file = NamedTemporaryFile(suffix=".crt")
client_key_file = NamedTemporaryFile(suffix=".key")

eboks_test_settings = {
    **settings.EBOKS,
    "client_cert": client_cert_file.name,
    "client_key": client_key_file.name,
}

pitu_test_settings = {
    "certificate": "test_cert",
    "private_key": "test_key",
    "root_ca": "test_ca",
    "client_header": "test_header",
    "base_url": "test_url",
    "person_info_service": "test_cpr_service",
    "company_info_service": "test_cvr_service",
}


@override_settings(EBOKS=eboks_test_settings)
@override_settings(PITU=pitu_test_settings)
@override_settings(
    ESKAT_BASE_URL="https://eskattest/eTaxCommonDataApi",
    ESKAT_USERNAME="testuser",
    ESKAT_PASSWORD="testpass",
    ESKAT_VERIFY=False,
)
class IntegrationBaseTest(
    PrismeMocks, EskatMocks, U1AMocks, DafoMocks, TransactionTestCase
):

    def setUp(self):
        self.stdout = StringIO()
        self.months_to_generate_btax_files_for = []
        self.year = 2024
        self.cpr = "1234567892"
        self.location_code = "956"
        super().setUp()

        call_command("load_prisme_account_aliases")

        calculation_method = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("60000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )

        # calculation_method should be entered manually by skattestyrelsen.
        # That is why we create a couple of years here and attach the calculation_method
        for year in [self.year - 1, self.year, self.year + 1]:
            Year.objects.create(year=year, calculation_method=calculation_method)

        # patch the default before creating any PersonYear objects to be
        # MonthlyContinuationEngine. This engine is easiest to understand and therefore
        # best for testing
        self.patcher = patch.object(
            PersonYear._meta.get_field("preferred_estimation_engine_a"),
            "default",
            "MonthlyContinuationEngine",
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def call_commands(
        self,
        effect_month,
        day_to_generate_btax_file_on=1,
        reraise=False,
    ):
        """
        Calls the job dispatcher for each day for a month.

        Notes
        ---------
        reraise can be set to True for debugging purposes. When reraise is False,
        jobs will silently fail without making a test explode.
        """
        effect_year = self.year

        year = effect_year
        month = effect_month + 2
        if month > 12:
            month -= 12
            year += 1

        months_to_generate_btax_files_for = self.months_to_generate_btax_files_for or [
            item["month"] for item in self.monthlyincome_json_data["data"]
        ]

        for day in get_days_in_month(year, month):

            if (
                month in months_to_generate_btax_files_for
                and day == day_to_generate_btax_file_on
            ):
                self.generate_btax_files(month, year)

            with patch(
                "django.utils.timezone.now",
                return_value=datetime(
                    year, month, day, 0, 0, 0, tzinfo=timezone.get_current_timezone()
                ),
            ):
                call_command("job_dispatcher", stdout=self.stdout, reraise=reraise)

    def assert_benefit(self, benefit_calculated, correct_benefit):
        """
        Compare calculated benefit to expected benefit

        Notes
        -------
        We allow a margin of +/- 12 kr to allow for rounding (We always round to the
        nearest krone when paying out)

        The margin is 12 because a rounding error every month of 1kr gives
        a 12 kr difference in December.
        """
        self.assertGreater(benefit_calculated, correct_benefit - 12)
        self.assertLess(benefit_calculated, correct_benefit + 12)

    def get_amount_sent_to_prisme(self, month):
        for call in self.prisme_mock.call_args_list:
            args, kwargs = call
            filename = args[3]

            if "G68_export" in filename and filename.endswith(
                f"{str(month).zfill(2)}.g68"
            ):
                content = args[1].read().decode("utf-8")
                args[1].seek(0)  # Reset so we can read this file again later
                parsed_content = G68Transaction.parse(content)

                for field in parsed_content:
                    if isinstance(field, Udbetalingsbeløb):
                        return int(field.val) / 10_000
        return 0

    def get_person_month(self, month):

        return PersonMonth.objects.get(
            person_year__person__cpr=self.cpr,
            month=month,
            person_year__year__year=self.year,
        )

    def assert_total_benefit(self, amount):

        total_amount = 0
        for month in range(1, 13):
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)
            total_amount += amount_sent_to_prisme

        self.assert_benefit(total_amount, amount)


class SteadyAverageIncomeTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            self.add_monthlyincome_record(self.cpr, month_number, income=20000)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=20000 * 12)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)
            self.assertEqual(person_month.estimated_year_result, 240_000)
            self.assert_benefit(amount_sent_to_prisme, 1312)

        self.assert_total_benefit(15_750)


class SteadyHighIncomeTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            self.add_monthlyincome_record(self.cpr, month_number, income=30000)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=30000 * 12)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)
            self.assertEqual(person_month.estimated_year_result, 360_000)
            self.assert_benefit(amount_sent_to_prisme, 735)

        self.assert_total_benefit(8_820)


class SteadyLowIncomeTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            self.add_monthlyincome_record(self.cpr, month_number, income=8000)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=8000 * 12)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)
            self.assertEqual(person_month.estimated_year_result, 96_000)
            self.assert_benefit(amount_sent_to_prisme, 379)

        self.assert_total_benefit(4_550)


class LowIncomeUntilJulyTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            income = 8000 if month_number < 7 else 0
            self.add_monthlyincome_record(self.cpr, month_number, income=income)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=8000 * 6)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

            if month < 7:
                self.assertEqual(person_month.estimated_year_result, 96_000)
                self.assert_benefit(amount_sent_to_prisme, 379)
            else:
                self.assertLess(person_month.estimated_year_result, 96_000)
                self.assertLess(person_month.benefit_calculated, 379)

        self.assert_total_benefit(2_280)


class LowIncomeFromJulyTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            income = 8000 if month_number >= 7 else 0
            self.add_monthlyincome_record(self.cpr, month_number, income=income)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=8000 * 6)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            person_month = self.get_person_month(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

            if month >= 7:
                self.assertEqual(person_month.estimated_year_result, 48_000)
            else:
                self.assertEqual(person_month.estimated_year_result, 0)
            self.assert_benefit(amount_sent_to_prisme, 0)

        self.assert_total_benefit(0)


class IncomeSpikeInJulyTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(1, 13):
            income = 500_000 if month_number == 7 else 8000
            self.add_monthlyincome_record(self.cpr, month_number, income=income)

        self.add_taxinformation_record(self.cpr, "FULL", (1, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=8000 * 11 + 500_000)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        for month in range(1, 13):
            self.call_commands(month)
            amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

            if month >= 7:
                self.assert_benefit(amount_sent_to_prisme, 0)
            else:
                self.assert_benefit(amount_sent_to_prisme, 379)

        self.assert_total_benefit(379 * 6)


class CalculateBenefitTaxScopeTest(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(7, 13):
            self.add_monthlyincome_record(self.cpr, month_number, income=20000)

        self.add_taxinformation_record(self.cpr, "FULL", (7, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=20000 * 6)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        """
        Test example 1 from https://redmine.magenta.dk/issues/65645#note-4:

        Eksempel: Borger skal have Suila-tapit, dukker op fra 1. juli

        Personen tjener 20.000 kroner pr. måned svarende til en årsindkomst på 240.000
        kroner og kommer til at tjene 120.000 som fuldt skattepligtig.

        Fra 1. juli har vi

        E = 6*20.000 = 120.000
        B = 120.000* (12/6) = 240.000

        Vedkommende vil derfor få 1312 kr. pr. måned i 6 måneder = 7872 kroner i alt.
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7:
                person_month = self.get_person_month(month)
                amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(amount_sent_to_prisme, 1312)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(1312 * 6)

    def test_estimate_and_calculate_benefit_default_engine(self):
        """
        Engine = InYearExtrapolationEngine is not so good at estimating annual income
        for people who are new to the job-market. Therefore the monthly amount that we
        pay out will not be nicely 1312 kr. every month.

        But the final transferred amount should still be the same (1312 * 6)
        """

        with patch.object(
            PersonYear._meta.get_field("preferred_estimation_engine_a"),
            "default",
            "InYearExtrapolationEngine",
        ):
            for month in range(1, 13):
                self.call_commands(month)

            self.assert_total_benefit(1312 * 6)


class CalculateBenefitTaxScopeTest2(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(9, 13):
            self.add_monthlyincome_record(self.cpr, month_number, income=50_000)

        self.add_taxinformation_record(self.cpr, "FULL", (9, 1), (12, 31))
        self.add_annualincome_record(self.cpr, salary=50_000 * 4)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        """
        Test example 2 from https://redmine.magenta.dk/issues/65645#note-4:

        Eksempel: Borger skal ikke have suila-tapit, dukker op 1. september

        Borgeren får kr. 50.000 om måneden, svarende til en årsindkomst på 600.000
        kroner.

        Vi har

        E = 200.000
        B = 200.000 * (12 / 4) = 600.000

        Vedkommende får derfor ingen suila-tapit.
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 9:
                person_month = self.get_person_month(month)
                amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

                self.assertEqual(person_month.estimated_year_result, 200_000)
                self.assert_benefit(amount_sent_to_prisme, 0)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(0)


class CalculateBenefitTaxScopeTest3(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(7, 10):
            self.add_monthlyincome_record(self.cpr, month_number, income=20000)

        self.add_taxinformation_record(self.cpr, "FULL", (7, 1), (9, 30))
        self.add_annualincome_record(self.cpr, salary=20000 * 4)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        """
        We cannot know in advance if a citizen will disappear in the course of a year
        Therefore we payout normally untill the citizen actually disappers. When the
        citizen has disappeared we do not payout
        """

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7 and month <= 9:
                person_month = self.get_person_month(month)
                amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(amount_sent_to_prisme, 1312)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(1312 * 3)


class CalculateBenefitTaxScopeTestNoTaxPeriod(IntegrationBaseTest):

    def setUp(self):
        super().setUp()

        for month_number in range(7, 10):
            self.add_monthlyincome_record(self.cpr, month_number, income=20000)

        self.add_annualincome_record(self.cpr, salary=20000 * 4)
        self.add_expectedincome_record(self.cpr, b_income=0)
        self.add_u1a_record(self.cpr, udbytte=0)

    def test_estimate_and_calculate_benefit(self):
        """
        If the person is not taxable we do not payout (But we still estimate!)
        """
        TaxInformationPeriod.objects.all().delete()

        for month in range(1, 13):
            self.call_commands(month)

            if month >= 7 and month <= 9:
                person_month = self.get_person_month(month)
                amount_sent_to_prisme = self.get_amount_sent_to_prisme(month)

                self.assertEqual(person_month.estimated_year_result, 120_000)
                self.assert_benefit(amount_sent_to_prisme, 0)
            else:
                with self.assertRaises(PersonMonth.DoesNotExist):
                    self.get_person_month(month)

        self.assert_total_benefit(0)
