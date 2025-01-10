# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from collections import defaultdict
from dataclasses import asdict, fields
from datetime import date
from decimal import Decimal
from typing import Dict, List, Set, TextIO

from common.utils import camelcase_to_snakecase, omit
from django.db import transaction
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from suila.integrations.eskat.responses.data_models import (
    AnnualIncome,
    ExpectedIncome,
    MonthlyIncome,
    TaxInformation,
)
from suila.models import AnnualIncome as AnnualIncomeModel
from suila.models import (
    DataLoad,
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    TaxScope,
    Year,
)


class Handler:

    @classmethod
    def create_person_years(
        cls,
        year_cpr_taxscopes: Dict[int, Dict[str, TaxScope | None]],
        load: DataLoad,
        out: TextIO,
        set_taxscope_on_missing: int | None = None,
    ) -> Dict[str, PersonYear] | None:

        person_years_count = 0
        person_years = {}
        for year, cpr_taxscopes in year_cpr_taxscopes.items():

            # Create or get Year objects
            year_obj, _ = Year.objects.get_or_create(year=year)

            # Create or update Person objects
            persons = {
                cpr: Person(cpr=cpr, name=cpr, load=load)
                for cpr in cpr_taxscopes.keys()
            }
            Person.objects.bulk_create(
                persons.values(),
                update_conflicts=True,
                update_fields=("cpr", "name"),
                unique_fields=("cpr",),
            )
            out.write(f"Processed {len(persons)} Person objects")

            # Update existing items in DB that are in the input
            to_update = []
            for person_year_1 in PersonYear.objects.filter(
                year=year, person__in=persons.values()
            ).select_related("person"):
                cpr = person_year_1.person.cpr
                tax_scope = cpr_taxscopes[cpr]
                if tax_scope is not None:  # only update if we have a taxscope to set
                    person_year_1.load = load
                    person_year_1.tax_scope = tax_scope
                    to_update.append(person_year_1)
                person_years[cpr] = person_year_1
            if len(to_update) > 0:
                bulk_update_with_history(
                    to_update, PersonYear, fields=("load", "tax_scope"), batch_size=1000
                )

            # Create new items in DB for items in the input
            to_create = []
            for cpr, person in persons.items():
                if cpr not in person_years:
                    person_year_2 = PersonYear(person=person, year=year_obj, load=load)
                    tax_scope = cpr_taxscopes[cpr]
                    if tax_scope is not None:
                        person_year_2.tax_scope = tax_scope
                    to_create.append(person_year_2)
                    person_years[cpr] = person_year_2
            created = bulk_create_with_history(to_create, PersonYear, batch_size=1000)
            person_years_count += len(created)

        # Update existing items in DB that are not in the input
        if set_taxscope_on_missing is not None:
            year_obj = Year.objects.get(year=set_taxscope_on_missing)

            to_update = list(
                PersonYear.objects.filter(year=year_obj).exclude(
                    person__cpr__in=person_years.keys()
                )
            )
            for person_year_3 in to_update:
                person_year_3.load = load
                person_year_3.tax_scope = TaxScope.FORSVUNDET_FRA_MANDTAL
            bulk_update_with_history(
                to_update, PersonYear, fields=("load", "tax_scope"), batch_size=1000
            )

        out.write(f"Processed {len(person_years)} PersonYear objects")
        return person_years


class AnnualIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> AnnualIncome:
        return AnnualIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls,
        items: List[AnnualIncome],
        load: DataLoad,
        out: TextIO,
    ):
        with transaction.atomic():
            year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(
                dict
            )
            for item in items:
                if item.year is not None and item.cpr is not None:
                    year_cpr_tax_scopes[item.year][item.cpr] = None
            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)
            if person_years:
                annual_incomes = [
                    AnnualIncomeModel(
                        person_year=person_years[item.cpr],
                        load=load,
                        **omit(asdict(item), "cpr", "year"),
                    )
                    for item in items
                    if item.cpr is not None
                ]
                AnnualIncomeModel.objects.bulk_create(annual_incomes)
                out.write(f"Created {len(annual_incomes)} AnnualIncome objects")


class ExpectedIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> ExpectedIncome:
        return ExpectedIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: List["ExpectedIncome"], load: DataLoad, out: TextIO
    ):
        with transaction.atomic():
            year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(
                dict
            )
            for item in items:
                if item.year is not None and item.cpr is not None:
                    year_cpr_tax_scopes[item.year][item.cpr] = None
            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)
            if person_years:
                assessments = [
                    PersonYearAssessment(
                        person_year=person_years[item.cpr],
                        load=load,
                        capital_income=item.capital_income or Decimal(0),
                        education_support_income=item.education_support_income
                        or Decimal(0),
                        care_fee_income=item.care_fee_income or Decimal(0),
                        alimony_income=item.alimony_income or Decimal(0),
                        other_b_income=item.other_b_income or Decimal(0),
                        gross_business_income=item.gross_business_income or Decimal(0),
                        # TODO: Tilret dette ud fra hvad Torben
                        #  svarer når han vender tilbage
                        brutto_b_income=sum(
                            filter(
                                None,
                                [
                                    item.capital_income,
                                    item.education_support_income,
                                    item.care_fee_income,
                                    item.alimony_income,
                                    item.other_b_income,
                                    item.gross_business_income,
                                ],
                            )
                        ),
                    )
                    for item in items
                    if item.cpr
                ]
                PersonYearAssessment.objects.bulk_create(assessments)
                out.write(f"Created {len(assessments)} PersonYearAssessment objects")


class MonthlyIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> MonthlyIncome:
        return MonthlyIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: List["MonthlyIncome"], load: DataLoad, out: TextIO
    ):
        with transaction.atomic():
            # Create Employer objects (for CVRs that we have not already created an
            # Employer object for.)
            Employer.objects.bulk_create(
                [
                    Employer(cvr=cvr, load=load)
                    for cvr in {int(item.cvr) for item in items if item.cvr}
                ],
                update_conflicts=True,
                update_fields=("load",),
                unique_fields=("cvr",),
            )
            # Construct dictionary mapping employer CVRs to Employer objects
            employer_map = {
                employer.cvr: employer for employer in Employer.objects.all()
            }

            data_months: Dict[int, Set[int]] = defaultdict(set)
            for item in items:
                if item.year is not None and item.month is not None:
                    data_months[item.year].add(item.month)

            # Create or update Year object
            year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(
                dict
            )
            for item in items:
                if item.year is not None and item.cpr is not None:
                    year_cpr_tax_scopes[item.year][item.cpr] = None
            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)
            if person_years:
                # Create or update PersonMonth objects
                person_months = {}
                for person_year in person_years.values():
                    for month in data_months[person_year.year.year]:
                        person_month = PersonMonth(
                            person_year=person_year,
                            load=load,
                            month=month,
                            import_date=date.today(),
                            amount_sum=Decimal(0),
                        )
                        key = (person_year.year_id, month, person_year.person.cpr)
                        person_months[key] = person_month
                PersonMonth.objects.bulk_create(
                    person_months.values(),
                    update_conflicts=True,
                    # Update existing object if it already exists
                    update_fields=("import_date",),
                    unique_fields=("person_year", "month"),
                )
                out.write(f"Processed {len(person_months)} PersonMonth objects")

                # Create MonthlyIncomeReport objects
                # (existing objects for this year will be deleted!)
                income_reports = []
                for item in items:
                    if (
                        item.cpr is not None
                        and item.year is not None
                        and item.month is not None
                    ):
                        person_month = person_months[(item.year, item.month, item.cpr)]
                        report = MonthlyIncomeReport(
                            person_month=person_month,
                            employer=(
                                employer_map[int(item.cvr)] if item.cvr else None
                            ),
                            load=load,
                            **{
                                f.name: Decimal(getattr(item, f.name) or 0)
                                for f in fields(item)
                                if f.name
                                not in {
                                    "cpr",
                                    "cvr",
                                    "tax_municipality_number",
                                    "month",
                                }
                            },
                        )
                        report.update_amount()
                        income_reports.append(report)
                MonthlyIncomeReport.objects.filter(
                    person_month__in=person_months.values()
                ).delete()
                MonthlyIncomeReport.objects.bulk_create(income_reports)
                for person_month in person_months.values():
                    person_month.update_amount_sum()
                out.write(f"Created {len(income_reports)} MonthlyIncomeReport objects")


class TaxInformationHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> TaxInformation:
        return TaxInformation(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: List["TaxInformation"], load: DataLoad, out: TextIO
    ):
        year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(dict)
        for item in items:
            if item.year is not None and item.cpr is not None:
                year_cpr_tax_scopes[item.year][item.cpr] = TaxScope.from_taxinformation(
                    item
                )
        with transaction.atomic():
            cls.create_person_years(
                year_cpr_tax_scopes,
                load,
                out,
                # Sæt eksisterende objekter på dette år,
                # som ikke er i year_cpr_tax_scopes, til forsvundet
                set_taxscope_on_missing=year,
            )
            # TODO: Brug data i items til at populere databasen
