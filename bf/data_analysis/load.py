# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
import sys
from dataclasses import asdict, dataclass, fields
from datetime import date
from decimal import Decimal
from io import StringIO, TextIOWrapper
from typing import Dict, List, TextIO, Type

from django.core.exceptions import ValidationError
from django.db import transaction

from bf.models import (
    Employer,
    FinalStatement,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    Year,
)


def list_get(list, index):
    try:
        return list[index]
    except IndexError:
        return None


@dataclass
class IndkomstCSVFileLine:
    cpr: str
    arbejdsgiver: str
    cvr: int
    a_amounts: List[int]
    b_amounts: List[int]
    low: int
    high: int
    sum: int

    @classmethod
    def from_csv_row(cls, row: List[str]):
        if len(row) > 3:
            return cls(
                cpr=list_get(row, 0),
                arbejdsgiver=list_get(row, 1),
                cvr=int(list_get(row, 2)),
                a_amounts=cls._get_columns(row, 3, 3 + 12),
                b_amounts=cls._get_columns(row, 3 + 12, 3 + 24),
                low=list_get(row, 3 + 24),
                high=list_get(row, 3 + 24 + 1),
                sum=list_get(row, 3 + 24 + 2),
            )

    @staticmethod
    def _get_column(row, index: int, default: int = 0) -> int:
        try:
            return int(row[index]) or default
        except (ValueError, IndexError):
            return default

    @staticmethod
    def _get_columns(row, start: int, end: int) -> list[int]:
        return [
            IndkomstCSVFileLine._get_column(row, index) for index in range(start, end)
        ]

    @classmethod
    def validate_header_labels(cls, labels: List[str]):
        expected = (
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
        )
        for i, label in enumerate(expected):
            if i >= len(labels) or label != labels[i]:
                raise ValidationError(f"Expected '{label}' in header at position {i}")

    @classmethod
    def create_or_update_objects(
        cls, year: int, rows: List["IndkomstCSVFileLine"], out: TextIO
    ):
        with transaction.atomic():
            # Create or update Year object
            year_obj, _ = Year.objects.get_or_create(year=year)

            # Create or update Person objects
            persons = {
                cpr: Person(cpr=cpr, name=cpr) for cpr in set(row.cpr for row in rows)
            }
            Person.objects.bulk_create(
                persons.values(),
                update_conflicts=True,
                update_fields=("cpr", "name"),
                unique_fields=("cpr",),
            )
            out.write(f"Processed {len(persons)} Person objects")

            # Create or update Employer objects
            employers = {cvr: Employer(cvr=cvr) for cvr in set(row.cvr for row in rows)}
            Employer.objects.bulk_create(
                employers.values(),
                update_conflicts=True,
                update_fields=("cvr",),
                unique_fields=("cvr",),
            )
            out.write(f"Processed {len(employers)} Employer objects")

            # Create or update PersonYear objects
            person_years = [
                PersonYear(person=person, year=year_obj) for person in persons.values()
            ]
            PersonYear.objects.bulk_create(
                person_years,
                update_conflicts=True,
                update_fields=("person", "year"),
                unique_fields=("person", "year"),
            )
            out.write(f"Processed {len(person_years)} PersonYear objects")

            # Create or update PersonMonth objects
            person_months = {}
            for person_year in person_years:
                for month in range(1, 13):
                    person_month = PersonMonth(
                        person_year=person_year,
                        month=month,
                        import_date=date.today(),
                        amount_sum=Decimal(0),
                    )
                    key = (person_year.person.cpr, month)
                    person_months[key] = person_month
            PersonMonth.objects.bulk_create(
                person_months.values(),
                update_conflicts=True,
                update_fields=("import_date",),
                unique_fields=("person_year", "month"),
            )
            out.write(f"Processed {len(person_months)} PersonMonth objects")

            # Create MonthlyAIncomeReport objects
            # (existing objects for this year will be deleted!)
            a_income_reports = []
            for row in rows:
                for index, amount in enumerate(row.a_amounts):
                    if amount != 0:
                        person_month = person_months[(row.cpr, (index % 12) + 1)]
                        a_income_reports.append(
                            MonthlyAIncomeReport(
                                person_month=person_month,
                                employer=employers[row.cvr],
                                amount=amount,
                            )
                        )
                        person_month.amount_sum += amount
                        person_month.save(update_fields=("amount_sum",))
            MonthlyAIncomeReport.objects.filter(
                person_month__person_year__year=year
            ).delete()
            MonthlyAIncomeReport.objects.bulk_create(a_income_reports)
            out.write(f"Created {len(a_income_reports)} MonthlyAIncomeReport objects")

            # Create MonthlyBIncomeReport objects
            # (existing objects for this year will be deleted!)
            b_income_reports = []
            for row in rows:
                for index, amount in enumerate(row.b_amounts):
                    if amount != 0:
                        person_month = person_months[(row.cpr, (index % 12) + 1)]
                        b_income_reports.append(
                            MonthlyBIncomeReport(
                                person_month=person_month,
                                trader=employers[row.cvr],
                                amount=amount,
                            )
                        )
                        person_month.amount_sum += amount
                        person_month.save(update_fields=("amount_sum",))
            MonthlyBIncomeReport.objects.filter(
                person_month__person_year__year=year
            ).delete()
            MonthlyBIncomeReport.objects.bulk_create(b_income_reports)
            out.write(f"Created {len(b_income_reports)} MonthlyBIncomeReport objects")


@dataclass
class AssessmentCSVFileLine:
    cpr: str
    renteindtægter: int
    uddannelsesstøtte: int
    honorarer: int
    underholdsbidrag: int
    andre_b: int
    brutto_b_før_erhvervsvirk_indhandling: int
    erhvervsindtægter_sum: int
    e2_indhandling: int
    brutto_b_indkomst: int

    @classmethod
    def validate_header_labels(cls, labels: List[str]):
        expected = (
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
        )
        for i, label in enumerate(expected):
            if i >= len(labels) or label != labels[i]:
                raise ValidationError(f"Expected '{label}' in header at position {i}")

    @classmethod
    def from_csv_row(cls, row: List[str]):
        if len(row) > 3:
            return cls(
                **{
                    field.name: list_get(row, index)
                    for (index, field) in enumerate(fields(cls))
                }
            )

    @classmethod
    def create_or_update_objects(
        cls, year: int, rows: List["AssessmentCSVFileLine"], out: TextIO
    ):
        with transaction.atomic():
            year_obj, _ = Year.objects.get_or_create(year=year)

            # Create or update Person objects
            persons = {
                cpr: Person(cpr=cpr, name=cpr) for cpr in set(row.cpr for row in rows)
            }
            Person.objects.bulk_create(
                persons.values(),
                update_conflicts=True,
                update_fields=("cpr", "name"),
                unique_fields=("cpr",),
            )
            out.write(f"Processed {len(persons)} Person objects")

            # Create or update PersonYear objects
            person_years = [
                PersonYear(person=person, year=year_obj) for person in persons.values()
            ]
            person_years_by_cpr = {
                person_year.person.cpr: person_year for person_year in person_years
            }
            PersonYear.objects.bulk_create(
                person_years,
                update_conflicts=True,
                update_fields=("person", "year"),
                unique_fields=("person", "year"),
            )
            out.write(f"Processed {len(person_years)} PersonYear objects")

            assessments = []
            for item in rows:
                person_year = person_years_by_cpr[item.cpr]
                model_data = asdict(item)
                del model_data["cpr"]
                assessments.append(
                    PersonYearAssessment(person_year=person_year, **model_data)
                )
            PersonYearAssessment.objects.bulk_create(assessments)
            out.write(f"Created {len(assessments)} PersonYearAssessment objects")


@dataclass
class FinalCSVFileLine:
    cpr: str
    skatteår: int
    lønindkomst: int
    offentlig_hjælp: int
    tjenestemandspension: int
    alderspension: int
    førtidspension: int
    arbejdsmarkedsydelse: int
    udenlandsk_pensionsbidrag: int
    tilskud_til_udenlandsk_pension: int
    dis_gis: int
    anden_indkomst: int
    renteindtægter_bank: int
    renteindtægter_obl: int
    andet_renteindtægt: int
    uddannelsesstøtte: int
    plejevederlag: int
    underholdsbidrag: int
    udbytte_udenlandske: int
    udenlandsk_indkomst: int
    frirejser: int
    gruppeliv: int
    lejeindtægter_ved_udlejning: int
    b_indkomst_andet: int
    fri_kost: int
    fri_logi: int
    fri_bolig: int
    fri_telefon: int
    fri_bil: int
    fri_internet: int
    fri_båd: int
    fri_andet: int
    renteudgift_realkredit: int
    renteudgift_bank: int
    renteudgift_esu: int
    renteudgift_bsu: int
    renteudgift_andet: int
    pensionsindbetaling: int
    omsætning_salg_på_brættet: int
    indhandling: int
    ekstraordinære_indtægter: int
    virksomhedsrenter: int
    virksomhedsrenter_indtægter: int
    virksomhedsrenter_udgifter: int
    skattemæssigt_resultat: int
    ejerandel_pct: int
    ejerandel_beløb: int
    a_indkomst: int
    b_indkomst: int
    skattefri_b_indkomst: int
    netto_b_indkomst: int
    standard_fradrag: int
    ligningsmæssig_fradrag: int
    anvendt_fradrag: int
    skattepligtig_indkomst: int

    @classmethod
    def validate_header_labels(cls, labels: List[str]):
        expected = (
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
        )
        for i, label in enumerate(expected):
            if i >= len(labels) or label != labels[i].strip():
                raise ValidationError(f"Expected '{label}' in header at position {i}")

    @classmethod
    def from_csv_row(cls, row: List[str]):
        if len(row) > 3:
            return cls(
                **{
                    field.name: list_get(row, index)
                    for (index, field) in enumerate(fields(cls))
                }
            )

    @classmethod
    def create_or_update_objects(
        cls, year: int, rows: List["FinalCSVFileLine"], out: TextIO
    ):
        years = set(row.cpr for row in rows)
        if len(years) > 1 or years.pop() != year:
            print("Found mismatching year in file")
            return
        year_obj, _ = Year.objects.get_or_create(year=year)

        # Create or update Person objects
        persons = {
            cpr: Person(cpr=cpr, name=cpr) for cpr in set(row.cpr for row in rows)
        }
        Person.objects.bulk_create(
            persons.values(),
            update_conflicts=True,
            update_fields=("cpr", "name"),
            unique_fields=("cpr",),
        )
        out.write(f"Processed {len(persons)} Person objects")

        # Create or update PersonYear objects
        person_years = [
            PersonYear(person=person, year=year_obj) for person in persons.values()
        ]
        person_years_by_cpr = {
            person_year.person.cpr: person_year for person_year in person_years
        }
        PersonYear.objects.bulk_create(
            person_years,
            update_conflicts=True,
            update_fields=("person", "year"),
            unique_fields=("person", "year"),
        )
        out.write(f"Processed {len(person_years)} PersonYear objects")

        final_statements = []
        for item in rows:
            person_year = person_years_by_cpr[item.cpr]
            model_data = asdict(item)
            del model_data["cpr"]
            del model_data["skatteår"]
            final_statements.append(
                FinalStatement(person_year=person_year, **model_data)
            )
        PersonYearAssessment.objects.bulk_create(final_statements)
        out.write(f"Created {len(final_statements)} FinalStatement objects")


type_map: Dict[str, Type[IndkomstCSVFileLine | AssessmentCSVFileLine]] = {
    "income": IndkomstCSVFileLine,
    "assessment": AssessmentCSVFileLine,
    "final_settlement": FinalCSVFileLine,
}


def load_csv(
    input: TextIOWrapper | StringIO,
    year: int,
    data_type: str,
    count: int,
    delimiter: str = ",",
    dry: bool = True,
    stdout: TextIO | None = None,
):
    data_class: Type[IndkomstCSVFileLine | AssessmentCSVFileLine | FinalCSVFileLine] = (
        type_map[data_type]
    )
    if stdout is None:
        stdout = sys.stdout

    reader = csv.reader(input, delimiter=delimiter)
    data_class.validate_header_labels(next(reader))

    rows = []
    for i, row in enumerate(reader):
        if count is not None and i >= count:
            break
        # We are not yet at last line in file. Parse it as a regular item
        line = data_class.from_csv_row(row)
        if line:
            rows.append(line)

    if dry:
        for row in rows:
            stdout.write(str(row))
            stdout.write("\n")
    else:
        data_class.create_or_update_objects(year, rows, stdout)
