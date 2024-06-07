import os
from csv import reader
from datetime import date
from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.db import connections
from django.test import TestCase

from bf.management.commands.import_persons_from_eskat import Command
from bf.models import Person, PersonMonth


class TestImportPersonsFromESkat(TestCase):
    databases = ["default", "eskat"]

    _expected_mandtal_cpr = "0101012222"
    _import_date = date(2020, 1, 1)

    def setUp(self):
        super().setUp()
        self._prepare_mock_eskat_db()
        self.command = Command()

    def test_create_new_person_from_mandtal(self):
        # Assert that we start from an empty state
        self._assert_empty_state()

        # Act: load data
        self._load_mock_eskat_db_fixture("mandtal.csv")
        output = self._call_command(self._import_date)

        # Assert that a new `Person` and `PersonMonth` is created
        self._assert_person_exists_with_name("Original Name")
        self._assert_person_month_exists(self._import_date)

        # Assert output matches expectation
        self.assertIn(
            "Created 1 new persons, updated 0 persons, "
            "created 1 new person months, and updated 0 person months.",
            output,
        )

    def test_updates_person_month_on_change(self):
        # Assert that we start from an empty state
        self._assert_empty_state()

        # 1. Load original data
        self._load_mock_eskat_db_fixture("mandtal.csv")
        output_1 = self._call_command(self._import_date)
        # 1. Assert original CPR data is imported
        self._assert_person_exists_with_name("Original Name")
        self._assert_person_month_exists(self._import_date, municipality_code=101)
        # 1. Assert output matches expectation
        self.assertIn(
            "Created 1 new persons, updated 0 persons, "
            "created 1 new person months, and updated 0 person months.",
            output_1,
        )

        # 2. Load updated data
        self._load_mock_eskat_db_fixture("mandtal_updated.csv")
        output_2 = self._call_command(self._import_date)
        # 2. Assert `Person` object is updated
        self._assert_person_exists_with_name("Updated Name")
        # 2. Assert `PersonMonth` object is not duplicated (due to two imports for the
        # same import date.) Assert `PersonMonth` is updated (the `municipality_code`
        # is updated.)
        self._assert_person_month_exists(self._import_date, municipality_code=102)
        # 2. Assert output matches expectation
        self.assertIn(
            "Created 0 new persons, updated 1 persons, "
            "created 0 new person months, and updated 1 person months.",
            output_2,
        )

    def test_creates_no_person_month_objects(self):
        # Assert that we start from an empty state:
        self._assert_empty_state()

        # Load empty dataset
        self._load_mock_eskat_db_fixture("mandtal_empty.csv")
        output = self._call_command(self._import_date)

        # Assert that no `Person` or `PersonMonth` objects have been created or updated
        self._assert_empty_state()
        self.assertIn(
            "Created 0 new persons, updated 0 persons, "
            "created 0 new person months, and updated 0 person months",
            output,
        )

    def _assert_empty_state(self):
        # Assert `Person` and `PersonMonth` data does not exist (yet)
        self.assertQuerySetEqual(Person.objects.all(), Person.objects.none())
        self.assertQuerySetEqual(PersonMonth.objects.all(), PersonMonth.objects.none())

    def _assert_person_exists_with_name(self, name: str):
        qs = Person.objects.filter(cpr=self._expected_mandtal_cpr).values_list(
            "cpr", "name"
        )
        self.assertQuerySetEqual(qs, [(self._expected_mandtal_cpr, name)])

    def _assert_person_month_exists(self, import_date: date, **field_values):
        self.assertQuerySetEqual(
            PersonMonth.objects.filter(import_date=import_date).values_list(
                "person__cpr",
                *field_values.keys(),
            ),
            [(self._expected_mandtal_cpr, *field_values.values())],
        )

    def _call_command(self, import_date: date) -> str:
        buf = StringIO()
        call_command(
            self.command,
            import_date.strftime("%Y-%m-%d"),
            stdout=buf,
            stderr=buf,
        )
        return buf.getvalue()

    def _prepare_mock_eskat_db(self):
        mock_eskat_db = connections["eskat"]
        with mock_eskat_db.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS eskat_mandtal")
            cursor.execute(
                """
                CREATE TABLE eskat_mandtal (
                    pt_census_guid UUID PRIMARY KEY,
                    cpr TEXT NOT NULL,
                    kommune_no INTEGER,
                    kommune TEXT,
                    navn TEXT,
                    adresselinje1 TEXT,
                    adresselinje2 TEXT,
                    adresselinje3 TEXT,
                    adresselinje4 TEXT,
                    adresselinje5 TEXT,
                    fuld_adresse TEXT,
                    skatteomfang TEXT,
                    skattedage INTEGER
                ) WITHOUT ROWID
                """
            )

    def _load_mock_eskat_db_fixture(self, name: str):
        # Load CSV
        csv_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../eskat/fixtures/",
            name,
        )
        with open(csv_path) as csv_file:
            rows = list(reader(csv_file, delimiter=";"))[1:]

        # Clear table and load CSV into it
        mock_eskat_db = connections["eskat"]
        with mock_eskat_db.cursor() as cursor:
            cursor.execute("DELETE FROM eskat_mandtal")
            cursor.executemany(
                """
                INSERT INTO
                    eskat_mandtal
                    (
                        pt_census_guid,
                        cpr,
                        kommune_no,
                        kommune,
                        navn,
                        adresselinje1,
                        adresselinje2,
                        adresselinje3,
                        adresselinje4,
                        adresselinje5,
                        fuld_adresse,
                        skatteomfang,
                        skattedage
                    )
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(str(uuid4()), *row) for row in rows],
            )
