# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import sys
from copy import copy
from decimal import Decimal
from io import StringIO, TextIOBase
from unittest import mock

from data_analysis.load import (
    AssessmentCSVFileLine,
    FileLine,
    FinalCSVFileLine,
    IndkomstCSVFileLine,
    load_csv,
)
from django.core.exceptions import ValidationError
from django.test import TestCase

from suila.models import (
    AnnualIncome,
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    Year,
)


class BaseTestCase(TestCase):

    class OutputWrapper(TextIOBase):

        def __init__(self, out, ending="\n"):
            self._out = out
            self.ending = ending

        def write(self, msg="", style_func=None, ending=None):
            pass


class LoadIncomeTest(BaseTestCase):

    @property
    def data(self):
        return StringIO(
            "CPR,Arbejdsgiver navn,Arbejdsgiver CVR,Jan a-indkomst,Feb a-indkomst,"
            "Mar a-indkomst,Apr a-indkomst,Maj a-indkomst,Jun a-indkomst,"
            "Jul a-indkomst,Aug a-indkomst,Sep a-indkomst,Okt a-indkomst,"
            "Nov a-indkomst,Dec a-indkomst,Jan indh.-indkomst,Feb indh.-indkomst,"
            "Mar indh.-indkomst,Apr indh.-indkomst,Maj indh.-indkomst,"
            "Jun indh.-indkomst,Jul indh.-indkomst,Aug indh.-indkomst,"
            "Sep indh.-indkomst,Okt indh.-indkomst,Nov indh.-indkomst,"
            "Dec indh.-indkomst,Laveste indkomst beløb,Højeste indkomst beløb,"
            "A-indkomst for året\n"
            "0,TestFirma,123,"
            "10000,10000,11000,12000,13000,12000,10000,11000,"
            "10000,11000,15000,0,"
            ",,,,,,5000,0,0,0,0,0,"
            "10000,15000,137000\n"
        )

    def test_list_get(self):
        self.assertEqual(FileLine.list_get([1, 2, 3], 2), 3)
        self.assertEqual(FileLine.list_get(["a", 2, 3], 0), "a")
        self.assertIsNone(FileLine.list_get([1, 2, 3], 3))

    def test_validate_header_labels(self):
        correct_labels = [
            "CPR",
            "Arbejdsgiver navn",
            "Arbejdsgiver CVR",
            "Jan a-indkomst",
            "Feb a-indkomst",
            "Mar a-indkomst",
            "Apr a-indkomst",
            "Maj a-indkomst",
            "Jun a-indkomst",
            "Jul a-indkomst",
            "Aug a-indkomst",
            "Sep a-indkomst",
            "Okt a-indkomst",
            "Nov a-indkomst",
            "Dec a-indkomst",
            "Jan indh.-indkomst",
            "Feb indh.-indkomst",
            "Mar indh.-indkomst",
            "Apr indh.-indkomst",
            "Maj indh.-indkomst",
            "Jun indh.-indkomst",
            "Jul indh.-indkomst",
            "Aug indh.-indkomst",
            "Sep indh.-indkomst",
            "Okt indh.-indkomst",
            "Nov indh.-indkomst",
            "Dec indh.-indkomst",
            "Laveste indkomst beløb",
            "Højeste indkomst beløb",
            "A-indkomst for året",
        ]
        IndkomstCSVFileLine.validate_header_labels(correct_labels)
        for i in range(len(correct_labels)):
            incorrect_labels = copy(correct_labels)
            incorrect_labels[i] = "foo"
            with self.assertRaises(ValidationError):
                IndkomstCSVFileLine.validate_header_labels(incorrect_labels)

    def test_dry(self):
        with StringIO() as buffer:
            load_csv(
                input=self.data,
                filename="testdata",
                year=2024,
                data_type="income",
                count=1,
                delimiter=",",
                dry=True,
                stdout=buffer,
            )
            buffer.seek(0)
            self.assertEqual(
                buffer.read(),
                "IndkomstCSVFileLine(cpr='0', arbejdsgiver='TestFirma', "
                "cvr=123, a_incomes=[10000, 10000, 11000, 12000, 13000, 12000, "
                "10000, 11000, 10000, 11000, 15000, 0], b_incomes=[0, 0, 0, "
                "0, 0, 0, 5000, 0, 0, 0, 0, 0], low='10000', high='15000', "
                "sum='137000')\n",
            )
        self.assertEqual(Year.objects.count(), 0)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Employer.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonMonth.objects.count(), 0)
        self.assertEqual(MonthlyIncomeReport.objects.count(), 0)

    def test_load(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="income",
            count=1,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        year = Year.objects.first()
        self.assertEqual(year.year, 2024)

        self.assertEqual(Person.objects.count(), 1)
        person = Person.objects.first()
        self.assertEqual(person.name, "0")
        self.assertEqual(person.cpr, "0")
        self.assertEqual(person.load.source, "csv")
        self.assertEqual(person.load.parameters["filename"], "testdata")

        self.assertEqual(PersonYear.objects.count(), 1)
        person_year = PersonYear.objects.first()
        self.assertEqual(person_year.person, person)
        self.assertEqual(person_year.year, year)
        self.assertEqual(person_year.load.source, "csv")
        self.assertEqual(person_year.load.parameters["filename"], "testdata")

        self.assertEqual(PersonMonth.objects.count(), 12)
        person_months = list(PersonMonth.objects.all().order_by("month"))
        for month, person_month in enumerate(person_months, 1):
            self.assertEqual(person_month.person, person)
            self.assertEqual(person_month.month, month)
            self.assertEqual(person_month.load.source, "csv")
            self.assertEqual(person_month.load.parameters["filename"], "testdata")

        self.assertEqual(MonthlyIncomeReport.objects.count(), 11)
        a_incomes = [
            report.a_income
            for report in MonthlyIncomeReport.objects.all().order_by("month")
        ]
        self.assertEqual(
            a_incomes,
            [
                Decimal("10000.00"),
                Decimal("10000.00"),
                Decimal("11000.00"),
                Decimal("12000.00"),
                Decimal("13000.00"),
                Decimal("12000.00"),
                Decimal("10000.00"),
                Decimal("11000.00"),
                Decimal("10000.00"),
                Decimal("11000.00"),
                Decimal("15000.00"),
            ],
        )
        for report in MonthlyIncomeReport.objects.all():
            self.assertEqual(report.load.source, "csv")
            self.assertEqual(report.load.parameters["filename"], "testdata")

        report = MonthlyIncomeReport.objects.filter(month=7).first()
        self.assertEqual(report.b_income, Decimal("5000.00"))
        self.assertEqual(report.month, 7)
        self.assertEqual(report.load.source, "csv")
        self.assertEqual(report.load.parameters["filename"], "testdata")

    def test_load_zero(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="income",
            count=0,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Employer.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonMonth.objects.count(), 0)
        self.assertEqual(MonthlyIncomeReport.objects.count(), 0)

    def test_from_csv_row_invalid_row(self):
        self.assertIsNone(IndkomstCSVFileLine.from_csv_row(["foo"]))


class LoadAssessmentTest(BaseTestCase):

    @property
    def data(self):
        return StringIO(
            "CPR,Renteind. pengeinstitut mm.,uddan. støtte,"
            '"Honorarer, plejevederlag mv.",Underholdsbidrag (hustrubidrag mv),'
            "Andre B-indkomster,Brutto B før erhvervsvirk. og indhandling,"
            "Erhvervsindtægter i alt,E2 Indhandling,Brutto B-indkomst\n"
            "0,1000,2000,3000,4000,5000,6000,7000,8000,9000\n"
        )

    def test_from_csv_row_invalid_row(self):
        self.assertIsNone(AssessmentCSVFileLine.from_csv_row(["foo"]))

    def test_validate_header_labels(self):
        correct_labels = [
            "CPR",
            "Renteind. pengeinstitut mm.",
            "uddan. støtte",
            "Honorarer, plejevederlag mv.",
            "Underholdsbidrag (hustrubidrag mv)",
            "Andre B-indkomster",
            "Brutto B før erhvervsvirk. og indhandling",
            "Erhvervsindtægter i alt",
            "E2 Indhandling",
            "Brutto B-indkomst",
        ]
        AssessmentCSVFileLine.validate_header_labels(correct_labels)
        for i in range(len(correct_labels)):
            incorrect_labels = copy(correct_labels)
            incorrect_labels[i] = "foo"
            with self.assertRaises(ValidationError):
                AssessmentCSVFileLine.validate_header_labels(incorrect_labels)

    def test_dry(self):
        with StringIO() as buffer:
            load_csv(
                input=self.data,
                filename="testdata",
                year=2024,
                data_type="assessment",
                count=1,
                delimiter=",",
                dry=True,
                stdout=buffer,
            )
            buffer.seek(0)
            self.assertEqual(
                buffer.read(),
                "AssessmentCSVFileLine(cpr='0', renteindtægter='1000', "
                "uddannelsesstøtte='2000', honorarer='3000', underholdsbidrag='4000', "
                "andre_b='5000', brutto_b_før_erhvervsvirk_indhandling='6000', "
                "erhvervsindtægter_sum='7000', e2_indhandling='8000', "
                "brutto_b_indkomst='9000')\n",
            )
        self.assertEqual(Year.objects.count(), 0)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)

    def test_load(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="assessment",
            count=1,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        year = Year.objects.first()
        self.assertEqual(year.year, 2024)

        self.assertEqual(Person.objects.count(), 1)
        person = Person.objects.first()
        self.assertEqual(person.name, "0")
        self.assertEqual(person.cpr, "0")

        self.assertEqual(PersonYear.objects.count(), 1)
        person_year = PersonYear.objects.first()
        self.assertEqual(person_year.person, person)
        self.assertEqual(person_year.year, year)

        self.assertEqual(PersonYearAssessment.objects.count(), 1)
        assessment = PersonYearAssessment.objects.first()
        self.assertEqual(assessment.person_year, person_year)
        self.assertEqual(assessment.capital_income, Decimal("1000.00"))
        self.assertEqual(assessment.education_support_income, Decimal("2000.00"))
        self.assertEqual(assessment.care_fee_income, Decimal("3000.00"))
        self.assertEqual(assessment.alimony_income, Decimal("4000.00"))
        self.assertEqual(assessment.other_b_income, Decimal("5000.00"))
        self.assertEqual(assessment.gross_business_income, Decimal("6000.00"))
        self.assertEqual(assessment.brutto_b_income, Decimal("9000.00"))
        self.assertEqual(assessment.load.source, "csv")
        self.assertEqual(assessment.load.parameters["filename"], "testdata")

    def test_load_zero(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="assessment",
            count=0,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)


class LoadAnnualIncomeTest(BaseTestCase):

    @property
    def data(self):
        return StringIO(
            "CPR,Skatteår,Lønindkomst,Offentlig hjælp,Tjenestemandspension,"
            "Alderspension,Førtidspension,Arbejdsmarkedsydelse,"
            "Udenlandsk pensionsbidrag,Tilskud til udenlandsk pension,DIS/GIS,"
            "Anden indkomst,Renteindtægter Bank,Renteindtægter Obl.,"
            "Andet renteindtægt,Uddannelsesstøtte,Plejevederlag,Underholdsbidrag,"
            "Udbytte udenlandske,Udenlandsk indkomst,Frirejser,Gruppeliv,"
            "Lejeindtægter ved udlejning,B-indkomst andet,Fri kost,Fri logi,"
            "Fri bolig,Fri telefon,Fri bil,Fri internet,Fri båd,Fri andet,"
            "Renteudgift realkredit,Renteudgift  Bank,Renteudgift ESU,"
            "Renteudgift BSU,Renteudgift andet,Pensionsindbetaling,"
            "Omsætning/salg på brættet,Indhandling ,Ekstraordinære - indtægter,"
            "Virksomhedsrenter,Virksomhedsrenter - indtægter,"
            "Virksomhedsrenter - udgifter,Skattemæssigt resultat,Ejerandel i %,"
            "Ejerandel beløb,A-indkomst,B-indkomst,Skattefri B-indkomst,"
            "Netto B-indkomst,Standard fradrag,Ligningsmæssig fradrag,"
            "Anvendt fradrag,Skattepligtig indkomst\n"
            "0,2024,50000,0,,,,,,,0,,0,0,0,0,0,0,,0,0,,,0,0,0,0,0,0,0,,0,0,0,0,"
            "0,,,,0,,0,,,0,0,0,50000,0,0,0,0,0,0,50000\n"
        )

    def test_from_csv_row_invalid_row(self):
        self.assertIsNone(FinalCSVFileLine.from_csv_row(["foo"]))

    def test_validate_header_labels(self):
        correct_labels = [
            "CPR",
            "Skatteår",
            "Lønindkomst",
            "Offentlig hjælp",
            "Tjenestemandspension",
            "Alderspension",
            "Førtidspension",
            "Arbejdsmarkedsydelse",
            "Udenlandsk pensionsbidrag",
            "Tilskud til udenlandsk pension",
            "DIS/GIS",
            "Anden indkomst",
            "Renteindtægter Bank",
            "Renteindtægter Obl.",
            "Andet renteindtægt",
            "Uddannelsesstøtte",
            "Plejevederlag",
            "Underholdsbidrag",
            "Udbytte udenlandske",
            "Udenlandsk indkomst",
            "Frirejser",
            "Gruppeliv",
            "Lejeindtægter ved udlejning",
            "B-indkomst andet",
            "Fri kost",
            "Fri logi",
            "Fri bolig",
            "Fri telefon",
            "Fri bil",
            "Fri internet",
            "Fri båd",
            "Fri andet",
            "Renteudgift realkredit",
            "Renteudgift  Bank",
            "Renteudgift ESU",
            "Renteudgift BSU",
            "Renteudgift andet",
            "Pensionsindbetaling",
            "Omsætning/salg på brættet",
            "Indhandling",
            "Ekstraordinære - indtægter",
            "Virksomhedsrenter",
            "Virksomhedsrenter - indtægter",
            "Virksomhedsrenter - udgifter",
            "Skattemæssigt resultat",
            "Ejerandel i %",
            "Ejerandel beløb",
            "A-indkomst",
            "B-indkomst",
            "Skattefri B-indkomst",
            "Netto B-indkomst",
            "Standard fradrag",
            "Ligningsmæssig fradrag",
            "Anvendt fradrag",
            "Skattepligtig indkomst",
        ]
        FinalCSVFileLine.validate_header_labels(correct_labels)
        for i in range(len(correct_labels)):
            incorrect_labels = copy(correct_labels)
            incorrect_labels[i] = "foo"
            with self.assertRaises(ValidationError):
                FinalCSVFileLine.validate_header_labels(incorrect_labels)

    def test_dry(self):
        with StringIO() as buffer:
            load_csv(
                input=self.data,
                filename="testdata",
                year=2024,
                data_type="final_settlement",
                count=1,
                delimiter=",",
                dry=True,
                stdout=buffer,
            )
            buffer.seek(0)
            self.assertEqual(
                buffer.read(),
                "FinalCSVFileLine(cpr='0', skatteår='2024', lønindkomst='50000', "
                "offentlig_hjælp='0', tjenestemandspension=None, alderspension=None, "
                "førtidspension=None, arbejdsmarkedsydelse=None, "
                "udenlandsk_pensionsbidrag=None, tilskud_til_udenlandsk_pension=None, "
                "dis_gis='0', anden_indkomst=None, renteindtægter_bank='0', "
                "renteindtægter_obl='0', andet_renteindtægt='0',"
                " uddannelsesstøtte='0', plejevederlag='0', underholdsbidrag='0',"
                " udbytte_udenlandske=None, udenlandsk_indkomst='0', frirejser='0',"
                " gruppeliv=None, lejeindtægter_ved_udlejning=None, "
                "b_indkomst_andet='0', fri_kost='0', fri_logi='0', fri_bolig='0',"
                " fri_telefon='0', fri_bil='0', "
                "fri_internet='0', fri_båd=None, fri_andet='0', "
                "renteudgift_realkredit='0', renteudgift_bank='0', "
                "renteudgift_esu='0', renteudgift_bsu='0', renteudgift_andet=None,"
                " pensionsindbetaling=None, omsætning_salg_på_brættet=None, "
                "indhandling='0', ekstraordinære_indtægter=None, "
                "virksomhedsrenter='0', virksomhedsrenter_indtægter=None, "
                "virksomhedsrenter_udgifter=None, skattemæssigt_resultat='0', "
                "ejerandel_pct='0', ejerandel_beløb='0', a_indkomst='50000', "
                "b_indkomst='0', skattefri_b_indkomst='0', netto_b_indkomst='0', "
                "standard_fradrag='0', ligningsmæssig_fradrag='0', "
                "anvendt_fradrag='0', skattepligtig_indkomst='50000')\n",
            )
        self.assertEqual(Year.objects.count(), 0)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)

    def test_load(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="final_settlement",
            count=1,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        year = Year.objects.first()
        self.assertEqual(year.year, 2024)

        self.assertEqual(Person.objects.count(), 1)
        person = Person.objects.first()
        self.assertEqual(person.name, "0")
        self.assertEqual(person.cpr, "0")

        self.assertEqual(PersonYear.objects.count(), 1)
        person_year = PersonYear.objects.first()
        self.assertEqual(person_year.person, person)
        self.assertEqual(person_year.year, year)

        self.assertEqual(AnnualIncome.objects.count(), 1)
        settlement = AnnualIncome.objects.first()
        self.assertEqual(settlement.person_year, person_year)

        self.assertEqual(settlement.salary, Decimal("50000.00"))
        self.assertEqual(settlement.public_assistance_income, Decimal(0))
        self.assertIsNone(settlement.retirement_pension_income)
        self.assertIsNone(settlement.disability_pension_income)
        self.assertIsNone(settlement.occupational_benefit)
        self.assertIsNone(settlement.foreign_pension_income)
        self.assertIsNone(settlement.subsidy_foreign_pension_income)
        self.assertEqual(settlement.dis_gis_income, Decimal(0))
        self.assertIsNone(settlement.other_a_income)
        self.assertEqual(settlement.deposit_interest_income, Decimal(0))
        self.assertEqual(settlement.bond_interest_income, Decimal(0))
        self.assertEqual(settlement.other_interest_income, Decimal(0))
        self.assertEqual(settlement.education_support_income, Decimal(0))
        self.assertEqual(settlement.care_fee_income, Decimal(0))
        self.assertEqual(settlement.alimony_income, Decimal(0))
        self.assertIsNone(settlement.foreign_dividend_income)
        self.assertEqual(settlement.foreign_income, Decimal(0))
        self.assertEqual(settlement.free_journey_income, Decimal(0))
        self.assertIsNone(settlement.group_life_income)
        self.assertIsNone(settlement.rental_income)
        self.assertEqual(settlement.other_b_income, Decimal(0))
        self.assertEqual(settlement.free_board_income, Decimal(0))
        self.assertEqual(settlement.free_lodging_income, Decimal(0))
        self.assertEqual(settlement.free_housing_income, Decimal(0))
        self.assertEqual(settlement.free_phone_income, Decimal(0))
        self.assertEqual(settlement.free_car_income, Decimal(0))
        self.assertEqual(settlement.free_internet_income, Decimal(0))
        self.assertIsNone(settlement.free_boat_income)
        self.assertEqual(settlement.free_other_income, Decimal(0))
        self.assertIsNone(settlement.pension_payment_income)
        self.assertIsNone(settlement.catch_sale_market_income)
        self.assertEqual(settlement.catch_sale_factory_income, Decimal(0))
        self.assertEqual(settlement.account_tax_result, Decimal(0))
        self.assertEqual(settlement.account_share_business_amount, Decimal(0))
        self.assertEqual(settlement.load.source, "csv")
        self.assertEqual(settlement.load.parameters["filename"], "testdata")

    def test_load_zero(self):
        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="final_settlement",
            count=0,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )
        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)

    @mock.patch("data_analysis.load.FinalCSVFileLine.from_csv_row")
    def test_load_invalid_lines(self, from_csv_row):
        from_csv_row.return_value = None

        load_csv(
            input=self.data,
            filename="testdata",
            year=2024,
            data_type="final_settlement",
            count=1,
            delimiter=",",
            dry=False,
            stdout=self.OutputWrapper(sys.stdout, ending="\n"),
        )

        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)

    def test_load_incorrect_year(self):

        with StringIO() as buffer:
            load_csv(
                input=self.data,
                filename="testdata",
                year=2023,
                data_type="final_settlement",
                count=1,
                delimiter=",",
                dry=False,
                stdout=buffer,
            )
            self.assertEqual(Year.objects.count(), 0)
            self.assertEqual(Person.objects.count(), 0)
            self.assertEqual(PersonYear.objects.count(), 0)
            self.assertEqual(PersonYearAssessment.objects.count(), 0)
            buffer.seek(0)
            self.assertEqual(buffer.read(), "Found mismatching year in file")
