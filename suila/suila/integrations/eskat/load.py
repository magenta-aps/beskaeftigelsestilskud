# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import re
from collections import defaultdict
from dataclasses import asdict, fields
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Set, TextIO

from common.utils import camelcase_to_snakecase, omit
from django.core.exceptions import ValidationError
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

logger = logging.getLogger(__name__)


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
            persons: dict[str, Person] = {}
            for cpr in cpr_taxscopes.keys():
                person = Person(cpr=cpr, name=cpr, load=load)
                try:
                    # Validate CPR against custom validator
                    person.full_clean(validate_unique=False)
                except ValidationError as exc:
                    logger.info("skipping Person: cpr=%r (error=%r)", cpr, exc)
                else:
                    persons[cpr] = person

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

    @classmethod
    def get_person_month(cls, cpr: str, year: int | None, month: int) -> PersonMonth:
        qs = PersonMonth.objects.select_related("person_year__person")
        person_month = qs.get(
            person_year__person__cpr=cpr,
            person_year__year__year=year,
            month=month,
        )
        return person_month

    @classmethod
    def get_person_year_assessment(cls, cpr: str, year: int) -> PersonYearAssessment:
        qs = PersonYearAssessment.objects.select_related(
            "person_year__year", "person_year__person"
        )
        person_year = qs.get(
            person_year__person__cpr=cpr,
            person_year__year__year=year,
        )
        return person_year

    @classmethod
    def get_field_values(
        cls,
        item: Any,
        default: int = 0,
        exclude: set[str] | None = None,
    ) -> dict[str, Any]:
        if exclude is None:
            exclude = set()
        return {
            f.name: Decimal(getattr(item, f.name) or default)
            for f in fields(item)
            if f.name not in exclude
        }


class AnnualIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> AnnualIncome:
        return AnnualIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls,
        items: Iterable[AnnualIncome],
        load: DataLoad,
        out: TextIO,
    ) -> list[AnnualIncomeModel]:
        with transaction.atomic():
            year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(
                dict
            )
            for item in items:
                if item.year is not None and item.cpr is not None:
                    year_cpr_tax_scopes[item.year][item.cpr] = None
            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)

            if person_years:
                objs_to_create = []
                objs_to_update = []

                for item in items:
                    if item.cpr is None or item.year is None:
                        print(
                            "Skipping item with empty CPR and/or year "
                            f"(cpr={item.cpr!r}, year={item.year!r})"
                        )
                        continue

                    field_values = omit(asdict(item), "cpr", "year")

                    try:
                        # Find existing `AnnualIncome` for this person year
                        annual_income = AnnualIncomeModel.objects.get(
                            person_year=person_years[item.cpr]
                        )
                    except AnnualIncomeModel.DoesNotExist:
                        # An existing `AnnualIncome` does not exist for this person year
                        # - create it.
                        annual_income = AnnualIncomeModel(
                            person_year=person_years[item.cpr],
                            load=load,
                            **field_values,
                        )
                        objs_to_create.append(annual_income)
                    else:
                        # An `AnnualIncome` exists for this person year - update it.
                        for name, value in field_values.items():
                            setattr(annual_income, name, value)
                        objs_to_update.append(annual_income)

                bulk_update_with_history(
                    objs_to_update,
                    AnnualIncomeModel,
                    [
                        f.name
                        for f in AnnualIncomeModel._meta.fields
                        if not f.primary_key
                    ],
                )

                bulk_create_with_history(objs_to_create, AnnualIncomeModel)

                out.write(f"Created {len(objs_to_create)} AnnualIncome objects")
                out.write(f"Updated {len(objs_to_update)} AnnualIncome objects")

                return objs_to_create + objs_to_update

        # Fall-through: return empty list
        return []


class ExpectedIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> ExpectedIncome:
        return ExpectedIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: Iterable["ExpectedIncome"], load: DataLoad, out: TextIO
    ) -> list[PersonYearAssessment]:
        with transaction.atomic():
            year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(
                dict
            )
            for item in items:
                if item.year is not None and item.cpr is not None:
                    year_cpr_tax_scopes[item.year][item.cpr] = None
            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)

            if person_years:
                objs_to_create = []
                objs_to_update = []

                for item in items:
                    if item.cpr is None or item.year is None:
                        print(
                            "Skipping item with empty CPR and/or year "
                            f"(cpr={item.cpr!r}, year={item.year!r})"
                        )
                        continue

                    field_values = cls.get_field_values(
                        item,
                        exclude={
                            # Exclude identifier fields
                            "cpr",
                            "year",
                            # Exclude fields not defined on `PersonYearAssessment`
                            "valid_from",
                            "do_expect_a_income",
                            "benefits_income",
                            "catch_sale_factory_income",
                            "catch_sale_market_income",
                            "bussiness_interest_income",
                            "extraordinary_bussiness_income",
                        },
                    )

                    # TODO: Tilret dette ud fra hvad Torben svarer når han vender
                    # tilbage
                    brutto_b_income = sum(
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
                    )

                    try:
                        # Find existing assessment
                        assessment = cls.get_person_year_assessment(item.cpr, item.year)
                    except PersonYearAssessment.DoesNotExist:
                        # An existing assessment does not exist for this person and year
                        # - create it.
                        assessment = PersonYearAssessment(
                            person_year=person_years[item.cpr],
                            load=load,
                            brutto_b_income=brutto_b_income,
                            **field_values,
                        )
                        objs_to_create.append(assessment)
                    else:
                        # An assessment exists for this person and year - update it.
                        for name, value in field_values.items():
                            setattr(assessment, name, value)
                        assessment.brutto_b_income = brutto_b_income
                        objs_to_update.append(assessment)

                bulk_update_with_history(
                    objs_to_update,
                    PersonYearAssessment,
                    [
                        f.name
                        for f in PersonYearAssessment._meta.fields
                        if not f.primary_key
                    ],
                )

                bulk_create_with_history(objs_to_create, PersonYearAssessment)

                out.write(f"Created {len(objs_to_create)} PersonYearAssessment objects")
                out.write(f"Updated {len(objs_to_update)} PersonYearAssessment objects")

                return objs_to_create + objs_to_update

        # Fall-through: return empty list
        return []


class MonthlyIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> MonthlyIncome:
        return MonthlyIncome(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: Iterable["MonthlyIncome"], load: DataLoad, out: TextIO
    ) -> list[PersonMonth]:
        data_months: Dict[int, Set[int]] = defaultdict(set)
        year_cpr_tax_scopes: Dict[int, Dict[str, TaxScope | None]] = defaultdict(dict)
        employers = []
        employer_cvrs = set()
        verified_monthly_income_reports: List["MonthlyIncome"] = []
        for item in items:
            if item.cvr and item.cvr not in employer_cvrs:
                employers.append(Employer(cvr=item.cvr, load=load))
                employer_cvrs.add(item.cvr)

            if item.year is not None and item.month is not None:
                data_months[item.year].add(item.month)

            if item.year is not None and item.cpr is not None:
                year_cpr_tax_scopes[item.year][item.cpr] = None

            # Verify the MonthlyIncome-instance have required data
            if item.cpr and bool(re.fullmatch(r"\d{10}", item.cpr)):
                verified_monthly_income_reports.append(item)
            else:
                logger.info(
                    'skipping MonthlyIncome: cpr=%r (error="invalid value for CPR")',
                    item.cpr,
                )
                continue

        with transaction.atomic():
            # Create Employer objects (for CVRs that we have not already created an
            # Employer object for.)
            if len(employers) > 0:
                Employer.objects.bulk_create(
                    employers,
                    update_conflicts=True,
                    update_fields=("load",),
                    unique_fields=("cvr",),
                )

            person_years = cls.create_person_years(year_cpr_tax_scopes, load, out)
            if person_years:
                # Create or update PersonMonth objects
                person_months: list[PersonMonth] = []
                for person_year in person_years.values():
                    for month in data_months[person_year.year.year]:
                        person_month = PersonMonth(
                            person_year=person_year,
                            load=load,
                            month=month,
                            import_date=date.today(),
                            amount_sum=Decimal(0),
                        )
                        person_months.append(person_month)

                PersonMonth.objects.bulk_create(
                    person_months,
                    update_conflicts=True,
                    update_fields=("load", "amount_sum", "import_date"),
                    unique_fields=("person_year", "month"),
                    batch_size=500,
                )
                out.write(f"Created {len(person_months)} PersonMonth objects")

                # Create IncomeReports
                # OBS: Uses PersonMonth instances, which is why these are created
                # before the IncomeReports.
                # OBS2: IncomeReports are handled before update of "amount_sum" for
                # PersonMonths, since this is based on the IncomeReports.
                income_reports = cls._create_or_update_monthly_income_reports(
                    verified_monthly_income_reports,
                    load,
                )
                out.write(
                    f"Created or updated {len(income_reports)} MonthlyIncomeReport "
                    "objects"
                )

                # Finally, update the PersonMonth's after creating the IncomeReports
                for person_month in person_months:
                    person_month.update_amount_sum()

                PersonMonth.objects.bulk_update(
                    person_months,
                    ["amount_sum"],
                    batch_size=500,
                )
                out.write(f"Updated {len(person_months)} PersonMonth objects")
                return person_months

        # Fall-through: return empty list (rather than None)
        return []

    @classmethod
    def _create_or_update_monthly_income_reports(
        cls,
        items: Iterable[MonthlyIncome],
        load: DataLoad,
    ) -> list:
        objs_to_create = []
        objs_to_update = []

        # Construct dictionary mapping employer CVRs to Employer objects
        employer_map = {employer.cvr: employer for employer in Employer.objects.all()}

        for item in items:
            if item.cpr is not None and item.month is not None:
                employer = employer_map[int(item.cvr)] if item.cvr else None
                person_month = cls.get_person_month(item.cpr, item.year, item.month)
                field_values = cls.get_field_values(
                    item,
                    exclude={"cpr", "cvr", "tax_municipality_number", "month"},
                )

                try:
                    # Find existing monthly income report
                    report = MonthlyIncomeReport.objects.get(
                        person_month=person_month,
                        employer=employer,
                    )
                except MonthlyIncomeReport.DoesNotExist:
                    # An existing monthly income report does not exist for this person
                    # month and employer - create it.
                    report = MonthlyIncomeReport(
                        person_month=person_month,
                        load=load,
                        employer=employer,
                        **field_values,
                    )
                    report.update_amount()
                    objs_to_create.append(report)
                else:
                    # An existing monthly income report exists for this person month and
                    # employer - update it.
                    for name, value in field_values.items():
                        setattr(report, name, value)
                    report.update_amount()
                    objs_to_update.append(report)

        bulk_update_with_history(
            objs_to_update,
            MonthlyIncomeReport,
            [f.name for f in MonthlyIncomeReport._meta.fields if not f.primary_key],
        )

        bulk_create_with_history(objs_to_create, MonthlyIncomeReport)

        return objs_to_create + objs_to_update


class TaxInformationHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> TaxInformation:
        return TaxInformation(**camelcase_to_snakecase(data))

    @classmethod
    def create_or_update_objects(
        cls, year: int, items: Iterable["TaxInformation"], load: DataLoad, out: TextIO
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
