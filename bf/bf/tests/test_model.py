from datetime import date

from django.test import TestCase

from bf.models import ASalaryReport, Employer, Person, PersonMonth, PersonYear


class ModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(name="Jens Hansen", cpr="1234567890")
        cls.year = PersonYear.objects.create(
            person=cls.person,
            year=2024,
        )
        cls.month = PersonMonth.objects.create(
            person_year=cls.year, month=6, import_date=date.today()
        )
        cls.employer = Employer.objects.create(
            name="Kolbøttefabrikken",
            cvr=12345678,
        )
        cls.report = ASalaryReport.objects.create(
            employer=cls.employer, person_month=cls.month, amount=100
        )

    def test_shortcuts(self):
        self.assertEqual(self.month.year, 2024)
        self.assertEqual(self.report.year, 2024)
        self.assertEqual(self.report.month, 6)

    def test_string_methods(self):
        self.assertEqual(str(self.person), "Jens Hansen")
        self.assertEqual(str(self.year), "Jens Hansen (2024)")
        self.assertEqual(str(self.month), "Jens Hansen (2024/6)")
        self.assertEqual(str(self.employer), "Kolbøttefabrikken (12345678)")
        self.assertEqual(
            str(self.report), "Jens Hansen (2024/6) | Kolbøttefabrikken (12345678)"
        )
