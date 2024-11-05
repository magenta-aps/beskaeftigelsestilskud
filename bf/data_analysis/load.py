# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
import sys
from collections.abc import Collection
from dataclasses import asdict, dataclass, fields
from datetime import date
from decimal import Decimal
from io import StringIO, TextIOWrapper
from typing import Dict, List, TextIO, Type

from django.core.exceptions import ValidationError
from django.db import transaction

from bf.models import (
    Employer,
    FinalSettlement,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    Year,
)


@dataclass(slots=True)
class FileLine:

    cpr: str

    @classmethod
    def list_get(cls, list, index):
        try:
            return list[index]
        except IndexError:
            return None

    @classmethod
    def get_value_or_none(cls, list, index):
        value = cls.list_get(list, index)
        if value == "":
            return None
        return value

    @classmethod
    def create_person_years(
        cls, year: int, rows: Collection["FileLine"], out: TextIO
    ) -> Dict[str, PersonYear] | None:

        # Create or get Year objects
        if len(rows) > 0 and "skatteår" in {f.name for f in fields(cls)}:
            years = {getattr(row, "skatteår") for row in rows}
            if len(years) > 1 or years.pop() != str(year):
                out.write("Found mismatching year in file")
                return None
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
        person_years = {
            person.cpr: PersonYear(person=person, year=year_obj)
            for person in persons.values()
        }
        PersonYear.objects.bulk_create(
            person_years.values(),
            update_conflicts=True,
            update_fields=("person", "year"),
            unique_fields=("person", "year"),
        )
        out.write(f"Processed {len(person_years)} PersonYear objects")
        return person_years


@dataclass(slots=True)
class IndkomstCSVFileLine(FileLine):
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
                cpr=cls.list_get(row, 0),
                arbejdsgiver=cls.list_get(row, 1),
                cvr=int(cls.list_get(row, 2)),
                a_amounts=cls._get_columns(row, 3, 3 + 12),
                b_amounts=cls._get_columns(row, 3 + 12, 3 + 24),
                low=cls.list_get(row, 3 + 24),
                high=cls.list_get(row, 3 + 24 + 1),
                sum=cls.list_get(row, 3 + 24 + 2),
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
            person_years = cls.create_person_years(year, rows, out)
            if person_years:
                # Create or update Employer objects
                employers = {
                    cvr: Employer(cvr=cvr) for cvr in set(row.cvr for row in rows)
                }
                Employer.objects.bulk_create(
                    employers.values(),
                    update_conflicts=True,
                    update_fields=("cvr",),
                    unique_fields=("cvr",),
                )
                out.write(f"Processed {len(employers)} Employer objects")

                # Create or update PersonMonth objects
                person_months = {}
                for person_year in person_years.values():
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
                            report = MonthlyAIncomeReport(
                                person_month=person_month,
                                employer=employers[row.cvr],
                                salary_income=amount,
                                amount=amount,
                            )
                            report.update_amount()
                            a_income_reports.append(report)
                MonthlyAIncomeReport.objects.filter(
                    person_month__person_year__year=year
                ).delete()
                MonthlyAIncomeReport.objects.bulk_create(a_income_reports)

                out.write(
                    f"Created {len(a_income_reports)} MonthlyAIncomeReport objects"
                )

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
                MonthlyBIncomeReport.objects.filter(
                    person_month__person_year__year=year
                ).delete()
                MonthlyBIncomeReport.objects.bulk_create(b_income_reports)
                out.write(
                    f"Created {len(b_income_reports)} MonthlyBIncomeReport objects"
                )

                for person_month in person_months.values():
                    person_month.update_amount_sum()
                    person_month.save(update_fields=("amount_sum",))


@dataclass(slots=True)
class AssessmentCSVFileLine(FileLine):
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
                    field.name: cls.list_get(row, index)
                    for (index, field) in enumerate(fields(cls))
                }
            )

    @classmethod
    def create_or_update_objects(
        cls, year: int, rows: List["AssessmentCSVFileLine"], out: TextIO
    ):
        with transaction.atomic():
            person_years = cls.create_person_years(year, rows, out)
            if person_years:
                assessments = []
                for item in rows:
                    person_year = person_years[item.cpr]
                    model_data = asdict(item)
                    del model_data["cpr"]
                    assessments.append(
                        PersonYearAssessment(person_year=person_year, **model_data)
                    )
                PersonYearAssessment.objects.bulk_create(assessments)
                out.write(f"Created {len(assessments)} PersonYearAssessment objects")


@dataclass(slots=True)
class FinalCSVFileLine(FileLine):
    skatteår: int
    lønindkomst: int | None
    offentlig_hjælp: int | None
    tjenestemandspension: int | None
    alderspension: int | None
    førtidspension: int | None
    arbejdsmarkedsydelse: int | None
    udenlandsk_pensionsbidrag: int | None
    tilskud_til_udenlandsk_pension: int | None
    dis_gis: int | None
    anden_indkomst: int | None
    renteindtægter_bank: int | None
    renteindtægter_obl: int | None
    andet_renteindtægt: int | None
    uddannelsesstøtte: int | None
    plejevederlag: int | None
    underholdsbidrag: int | None
    udbytte_udenlandske: int | None
    udenlandsk_indkomst: int | None
    frirejser: int | None
    gruppeliv: int | None
    lejeindtægter_ved_udlejning: int | None
    b_indkomst_andet: int | None
    fri_kost: int | None
    fri_logi: int | None
    fri_bolig: int | None
    fri_telefon: int | None
    fri_bil: int | None
    fri_internet: int | None
    fri_båd: int | None
    fri_andet: int | None
    renteudgift_realkredit: int | None
    renteudgift_bank: int | None
    renteudgift_esu: int | None
    renteudgift_bsu: int | None
    renteudgift_andet: int | None
    pensionsindbetaling: int | None
    omsætning_salg_på_brættet: int | None
    indhandling: int | None
    ekstraordinære_indtægter: int | None
    virksomhedsrenter: int | None
    virksomhedsrenter_indtægter: int | None
    virksomhedsrenter_udgifter: int | None
    skattemæssigt_resultat: int | None
    ejerandel_pct: int | None
    ejerandel_beløb: int | None
    a_indkomst: int | None
    b_indkomst: int | None
    skattefri_b_indkomst: int | None
    netto_b_indkomst: int | None
    standard_fradrag: int | None
    ligningsmæssig_fradrag: int | None
    anvendt_fradrag: int | None
    skattepligtig_indkomst: int | None

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
                    field.name: cls.get_value_or_none(row, index)
                    for (index, field) in enumerate(fields(cls))
                }
            )

    @classmethod
    def create_or_update_objects(
        cls, year: int, rows: List["FinalCSVFileLine"], out: TextIO
    ):
        person_years = cls.create_person_years(year, rows, out)
        if person_years:
            final_statements = []
            for item in rows:
                person_year = person_years[item.cpr]
                model_data = asdict(item)
                del model_data["cpr"]
                del model_data["skatteår"]
                final_statements.append(
                    FinalSettlement(person_year=person_year, **model_data)
                )
            FinalSettlement.objects.bulk_create(final_statements)
            out.write(f"Created {len(final_statements)} FinalStatement objects")


type_map: Dict[
    str, Type[IndkomstCSVFileLine | AssessmentCSVFileLine | FinalCSVFileLine]
] = {
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
    stdout: TextIO = sys.stdout,
):
    data_class: Type[IndkomstCSVFileLine | AssessmentCSVFileLine | FinalCSVFileLine] = (
        type_map[data_type]
    )

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
