# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from copy import copy
from decimal import Decimal
from io import StringIO

from data_analysis.load import (
    AssessmentCVRFileLine,
    IndkomstCSVFileLine,
    list_get,
    load_csv,
)
from django.core.exceptions import ValidationError
from django.test import TestCase

from bf.models import (
    Employer,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    Year,
)


class LoadIncomeTest(TestCase):

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
            "0,TestFirma,123,10000,10000,11000,12000,13000,12000,10000,11000,"
            "10000,11000,15000,12000,,,,,,,5000,0,0,0,0,0,10000,15000,137000\n"
        )

    def test_list_get(self):
        self.assertEqual(list_get([1, 2, 3], 2), 3)
        self.assertEqual(list_get(["a", 2, 3], 0), "a")
        self.assertIsNone(list_get([1, 2, 3], 3))

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
                "cvr=123, a_amounts=[10000, 10000, 11000, 12000, 13000, 12000, "
                "10000, 11000, 10000, 11000, 15000, 12000], b_amounts=[0, 0, 0, "
                "0, 0, 0, 5000, 0, 0, 0, 0, 0], low='10000', high='15000', "
                "sum='137000')\n",
            )
        self.assertEqual(Year.objects.count(), 0)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Employer.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonMonth.objects.count(), 0)
        self.assertEqual(MonthlyAIncomeReport.objects.count(), 0)

    def test_load(self):
        load_csv(
            input=self.data,
            year=2024,
            data_type="income",
            count=1,
            delimiter=",",
            dry=False,
            stdout=None,
        )
        self.assertEqual(Year.objects.count(), 1)
        year = Year.objects.first()
        self.assertEqual(year.year, 2024)

        self.assertEqual(Person.objects.count(), 1)
        person = Person.objects.first()
        self.assertEqual(person.name, "0")
        self.assertEqual(person.cpr, "0")

        self.assertEqual(Employer.objects.count(), 1)
        employer = Employer.objects.first()
        self.assertEqual(employer.cvr, 123)

        self.assertEqual(PersonYear.objects.count(), 1)
        person_year = PersonYear.objects.first()
        self.assertEqual(person_year.person, person)
        self.assertEqual(person_year.year, year)

        self.assertEqual(PersonMonth.objects.count(), 12)
        person_months = list(PersonMonth.objects.all().order_by("month"))
        for month, person_month in enumerate(person_months, 1):
            self.assertEqual(person_month.person, person)
            self.assertEqual(person_month.month, month)

        self.assertEqual(MonthlyAIncomeReport.objects.count(), 12)
        a_incomes = [
            report.amount
            for report in MonthlyAIncomeReport.objects.all().order_by("month")
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
                Decimal("12000.00"),
            ],
        )

        self.assertEqual(MonthlyBIncomeReport.objects.count(), 1)
        report = MonthlyBIncomeReport.objects.first()
        self.assertEqual(report.amount, Decimal("5000.00"))
        self.assertEqual(report.month, 7)

    def test_load_zero(self):
        load_csv(
            input=self.data,
            year=2024,
            data_type="income",
            count=0,
            delimiter=",",
            dry=False,
            stdout=None,
        )
        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Employer.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonMonth.objects.count(), 0)
        self.assertEqual(MonthlyAIncomeReport.objects.count(), 0)


class LoadAssessmentTest(TestCase):

    @property
    def data(self):
        return StringIO(
            "CPR,Renteind. pengeinstitut mm.,uddan. støtte,"
            '"Honorarer, plejevederlag mv.",Underholdsbidrag (hustrubidrag mv),'
            "Andre B-indkomster,Brutto B før erhvervsvirk. og indhandling,"
            "Erhvervsindtægter i alt,E2 Indhandling,Brutto B-indkomst\n"
            "0,1000,2000,3000,4000,5000,6000,7000,8000,9000\n"
        )

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
        AssessmentCVRFileLine.validate_header_labels(correct_labels)
        for i in range(len(correct_labels)):
            incorrect_labels = copy(correct_labels)
            incorrect_labels[i] = "foo"
            with self.assertRaises(ValidationError):
                AssessmentCVRFileLine.validate_header_labels(incorrect_labels)

    def test_dry(self):
        with StringIO() as buffer:
            load_csv(
                input=self.data,
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
                "AssessmentCVRFileLine(cpr='0', renteindtægter='1000', "
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
            year=2024,
            data_type="assessment",
            count=1,
            delimiter=",",
            dry=False,
            stdout=None,
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
        self.assertEqual(assessment.renteindtægter, Decimal("1000.00"))
        self.assertEqual(assessment.uddannelsesstøtte, Decimal("2000.00"))
        self.assertEqual(assessment.honorarer, Decimal("3000.00"))
        self.assertEqual(assessment.underholdsbidrag, Decimal("4000.00"))
        self.assertEqual(assessment.andre_b, Decimal("5000.00"))
        self.assertEqual(
            assessment.brutto_b_før_erhvervsvirk_indhandling, Decimal("6000.00")
        )
        self.assertEqual(assessment.erhvervsindtægter_sum, Decimal("7000.00"))
        self.assertEqual(assessment.e2_indhandling, Decimal("8000.00"))
        self.assertEqual(assessment.brutto_b_indkomst, Decimal("9000.00"))

    def test_load_zero(self):
        load_csv(
            input=self.data,
            year=2024,
            data_type="assessment",
            count=0,
            delimiter=",",
            dry=False,
            stdout=None,
        )
        self.assertEqual(Year.objects.count(), 1)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonYear.objects.count(), 0)
        self.assertEqual(PersonYearAssessment.objects.count(), 0)
