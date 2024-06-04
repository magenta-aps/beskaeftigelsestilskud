import os
from csv import reader
from datetime import date
from uuid import uuid4

from django.db import connections
from django.test import TestCase
from eskat.models import ESkatMandtal

from bf.management.commands.import_persons_from_eskat import Command
from bf.models import PersonMonth


class TestImportPersonsFromESkat(TestCase):
    databases = ["default", "eskat"]

    def setUp(self):
        super().setUp()
        self._prepare_mock_eskat_db()
        self.command = Command()

    def test_creates_person_month_objects(self):
        # Load data for January 2020
        self._load_mock_eskat_db_fixture("mandtal.csv")
        self.command.handle(import_date="2020-01-01")
        # Assert that objects have been created for each CPR
        self.assertQuerySetEqual(
            PersonMonth.objects.filter(import_date=date(2020, 1, 1)).values_list(
                "cpr", flat=True
            ),
            ESkatMandtal.objects.values_list("cpr", flat=True),
        )

    def test_updates_person_month_on_change(self):
        # Load original data for January 2020
        self._load_mock_eskat_db_fixture("mandtal.csv")
        self.command.handle(import_date="2020-01-01")
        # Assert original CPR data is imported
        self.assertQuerySetEqual(
            PersonMonth.objects.filter(
                import_date=date(2020, 1, 1),
                cpr="0101012222",
            ).values_list("name", flat=True),
            ["Original Name"],
        )

        # Load updated data for January 2020
        self._load_mock_eskat_db_fixture("mandtal_updated.csv")
        self.command.handle(import_date="2020-01-01")
        # Assert person month object is updated
        self.assertQuerySetEqual(
            PersonMonth.objects.filter(
                import_date=date(2020, 1, 1),
                cpr="0101012222",
            ).values_list("name", flat=True),
            ["Updated Name"],
        )

    def test_creates_no_person_month_objects(self):
        # Load data for February 2020 (empty set)
        self._load_mock_eskat_db_fixture("mandtal_empty.csv")
        self.command.handle(import_date="2020-02-01")
        # Assert that no person months exist for February
        self.assertQuerySetEqual(
            PersonMonth.objects.filter(import_date=date(2020, 2, 1)),
            PersonMonth.objects.none(),
        )

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
