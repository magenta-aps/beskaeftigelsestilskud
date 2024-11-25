# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

import csv
import sys
from collections.abc import Collection
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from io import StringIO, TextIOWrapper
from typing import Dict, List, TextIO, Type

from django.core.exceptions import ValidationError
from django.db import transaction

from bf.models import (
    AnnualIncome,
    DataLoad,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    TaxScope,
    Year,
)


def asdict(item):

    translation_dict = {
        "lønindkomst": "salary",
        "offentlig_hjælp": "social_benefit_income",
        "alderspension": "retirement_pension_income",
        "førtidspension": "disability_pension_income",
        # "??": "ignored_benefits",
        "arbejdsmarkedsydelse": "occupational_benefit",
        "udenlandsk_pensionsbidrag": "foreign_pension_income",
        "tilskud_til_udenlandsk_pension": "subsidy_foreign_pension_income",
        "dis_gis": "dis_gis_income",
        "anden_indkomst": "other_a_income",
        "renteindtægter_bank": "deposit_interest_income",
        "renteindtægter_obl": "bond_interest_income",
        "andet_renteindtægt": "other_interest_income",
        "uddannelsesstøtte": "education_support_income",
        "plejevederlag": "care_fee_income",
        "underholdsbidrag": "alimony_income",
        "udbytte_udenlandske": "foreign_dividend_income",
        "udenlandsk_indkomst": "foreign_income",
        "frirejser": "free_journey_income",
        "gruppeliv": "group_life_income",
        "lejeindtægter_ved_udlejning": "rental_income",
        "b_indkomst_andet": "other_b_income",
        "fri_kost": "free_board_income",
        "fri_logi": "free_lodging_income",
        "fri_bolig": "free_housing_income",
        "fri_telefon": "free_phone_income",
        "fri_bil": "free_car_income",
        "fri_internet": "free_internet_income",
        "fri_båd": "free_boat_income",
        "fri_andet": "free_other_income",
        "renteudgift_andet": "other_debt_interest_income",
        "pensionsindbetaling": "pension_payment_income",
        "omsætning_salg_på_brættet": "catch_sale_market_income",
        "indhandling": "catch_sale_factory_income",
        "ekstraordinære_indtægter": "account_extraord_entries_income",
        "virksomhedsrenter": "account_business_interest",
        "virksomhedsrenter_indtægter": "account_business_interest_income",
        "virksomhedsrenter_udgifter": "account_business_interest_deduct",
        "skattemæssigt_resultat": "account_tax_result",
        "ejerandel_pct": "account_share_business_percentage",
        "ejerandel_beløb": "account_share_business_amount",
        # "??": "shareholder_dividend_income",
        "renteindtægter": "capital_income",
        "honorarer": "care_fee_income",
        "andre_b": "other_b_income",
        "brutto_b_før_erhvervsvirk_indhandling": "gross_business_income",
        "brutto_b_indkomst": "brutto_b_income",
    }

    cols = [c for c in dir(item) if c in translation_dict]
    return {translation_dict.get(col): getattr(item, col) for col in cols}


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
        cls, year: int, rows: Collection["FileLine"], load: DataLoad, out: TextIO
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
            cpr: Person(cpr=cpr, name=cpr, load=load)
            for cpr in set(row.cpr for row in rows)
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
            person.cpr: PersonYear(
                person=person,
                year=year_obj,
                load=load,
                tax_scope=TaxScope.FULDT_SKATTEPLIGTIG,
            )
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
    a_incomes: List[int]
    b_incomes: List[int]
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
                a_incomes=cls._get_columns(row, 3, 3 + 12),
                b_incomes=cls._get_columns(row, 3 + 12, 3 + 24),
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
        cls, year: int, rows: List["IndkomstCSVFileLine"], load: DataLoad, out: TextIO
    ):
        with transaction.atomic():
            # Create or update Year object
            person_years = cls.create_person_years(year, rows, load, out)
            if person_years:

                # Create or update PersonMonth objects
                person_months = {}
                for person_year in person_years.values():
                    for month in range(1, 13):
                        person_month = PersonMonth(
                            person_year=person_year,
                            month=month,
                            import_date=date.today(),
                            amount_sum=Decimal(0),
                            load=load,
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

                # Create MonthlyIncomeReport objects
                # (existing objects for this year will be deleted!)
                income_reports: List[MonthlyIncomeReport] = []
                for row in rows:
                    person_income_reports: Dict[int, MonthlyIncomeReport] = {}
                    for report_field, amounts in (
                        ("salary_income", row.a_incomes),
                        ("capital_income", row.b_incomes),
                    ):
                        for index, income in enumerate(amounts):
                            if income != 0:
                                person_month = person_months[
                                    (row.cpr, (index % 12) + 1)
                                ]
                                if index in person_income_reports:
                                    report = person_income_reports[index]
                                else:
                                    report = MonthlyIncomeReport(
                                        person_month=person_month,
                                        load=load,
                                    )
                                    person_income_reports[index] = report
                                setattr(report, report_field, income)
                    for report in person_income_reports.values():
                        report.update_amount()
                    income_reports += person_income_reports.values()
                MonthlyIncomeReport.objects.filter(
                    person_month__person_year__year=year
                ).delete()
                MonthlyIncomeReport.objects.bulk_create(income_reports)

                out.write(f"Created {len(income_reports)} MonthlyIncomeReport objects")
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
        cls, year: int, rows: List["AssessmentCSVFileLine"], load: DataLoad, out: TextIO
    ):
        with transaction.atomic():
            person_years = cls.create_person_years(year, rows, load, out)
            if person_years:
                assessments = []
                for item in rows:
                    person_year = person_years[item.cpr]
                    model_data = asdict(item)
                    assessments.append(
                        PersonYearAssessment(
                            person_year=person_year, load=load, **model_data
                        )
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
        cls, year: int, rows: List["FinalCSVFileLine"], load: DataLoad, out: TextIO
    ):
        person_years = cls.create_person_years(year, rows, load, out)
        if person_years:
            final_statements = []
            for item in rows:
                person_year = person_years[item.cpr]
                model_data = asdict(item)
                final_statements.append(
                    AnnualIncome(person_year=person_year, load=load, **model_data)
                )
            AnnualIncome.objects.filter(person_year__in=person_years.values()).delete()
            AnnualIncome.objects.bulk_create(final_statements)
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
    filename: str,
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
    load = DataLoad.objects.create(source="csv", parameters={"filename": filename})

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
        data_class.create_or_update_objects(year, rows, load, stdout)
