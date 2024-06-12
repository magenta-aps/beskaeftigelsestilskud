from datetime import date

from django.test import TestCase

from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear


class ModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(cpr="1234567890")
        cls.year = PersonYear.objects.create(
            person=cls.person,
            year=2024,
        )
        cls.month = PersonMonth.objects.create(
            person_year=cls.year, month=6, import_date=date.today()
        )
        cls.employer = Employer.objects.create(
            cvr=12345678,
        )
        cls.report = ASalaryReport.objects.create(
            employer=cls.employer, person_month=cls.month, amount=100
        )

    def test_shortcuts(self):
        self.assertEqual(self.month.year, 2024)
        self.assertEqual(self.report.year, 2024)
        self.assertEqual(self.report.month, 6)
