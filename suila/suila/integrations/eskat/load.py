# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import logging
import re
from collections import defaultdict
from dataclasses import asdict, fields
from datetime import date, datetime
from decimal import Decimal
from itertools import batched
from typing import Any, Dict, Iterable, List, Set, TextIO

from common.utils import camelcase_to_snakecase, omit
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
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
    ) -> Dict[str, PersonYear] | None:
        person_years_count = 0
        person_years = {}

        for year, cpr_taxscopes in year_cpr_taxscopes.items():
            # Create or get Year objects
            year_obj, _ = Year.objects.get_or_create(year=year)

            # Create or update Person objects
            persons: dict[str, Person] = {}
            for cpr in cpr_taxscopes.keys():
                person = Person(cpr=cpr, load=load)
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
    def get_person_year_assessment(
        cls, cpr: str, year: int, valid_from: datetime
    ) -> PersonYearAssessment:
        qs = PersonYearAssessment.objects.select_related(
            "person_year__year", "person_year__person"
        )
        person_year = qs.get(
            person_year__person__cpr=cpr,
            person_year__year__year=year,
            valid_from=valid_from,
        )
        return person_year

    @classmethod
    def parse_value(cls, name: str, value: Any) -> Any:
        if name == "valid_from":
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.get_current_timezone()
            )
        return Decimal(value)

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
            f.name: cls.parse_value(f.name, getattr(item, f.name) or default)
            for f in fields(item)
            if f.name not in exclude
        }

    @staticmethod
    def sanitize_api_dict(dataclass, data: Dict[str, str | int | bool | float]):
        data_dict = camelcase_to_snakecase(data)
        valid_keys = {field.name for field in dataclass.__dataclass_fields__.values()}
        return {k: v for k, v in data_dict.items() if k in valid_keys}


class AnnualIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> AnnualIncome:
        return AnnualIncome(**Handler.sanitize_api_dict(AnnualIncome, data))

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
                objs_to_create = {}
                objs_to_update = {}
                postponed = []

                for item in items:
                    if item.cpr is None or item.year is None:
                        print(
                            "Skipping item with empty CPR and/or year "
                            f"(cpr={item.cpr!r}, year={item.year!r})"
                        )
                        continue

                    field_values = omit(asdict(item), "cpr", "year")
                    key = (item.cpr, item.year)
                    if key in objs_to_create:
                        postponed.append(item)
                    else:
                        try:
                            # Find existing `AnnualIncome` for this person year
                            annual_income = AnnualIncomeModel.objects.get(
                                person_year=person_years[item.cpr]
                            )
                        except AnnualIncomeModel.DoesNotExist:
                            # An existing `AnnualIncome` does not exist
                            # for this person year
                            # - create it.
                            annual_income = AnnualIncomeModel(
                                person_year=person_years[item.cpr],
                                load=load,
                                **field_values,
                            )
                            objs_to_create[key] = annual_income
                        else:
                            # An `AnnualIncome` exists for this person year - update it.
                            changed = False
                            for name, value in field_values.items():
                                if getattr(annual_income, name) != value:
                                    setattr(annual_income, name, value)
                                    changed = True
                            if changed:
                                objs_to_update[key] = annual_income

                objs_to_create_list = list(objs_to_create.values())
                objs_to_update_list = list(objs_to_update.values())

                bulk_create_with_history(
                    objs_to_create_list,
                    AnnualIncomeModel,
                )
                bulk_update_with_history(
                    objs_to_update_list,
                    AnnualIncomeModel,
                    [
                        f.name
                        for f in AnnualIncomeModel._meta.fields
                        if not f.primary_key
                    ],
                )

                out.write(f"Created {len(objs_to_create_list)} AnnualIncome objects")
                out.write(f"Updated {len(objs_to_update_list)} AnnualIncome objects")

                if postponed:
                    objs_to_update_list += cls.create_or_update_objects(
                        postponed, load, out
                    )

                return objs_to_create_list + objs_to_update_list

        # Fall-through: return empty list
        return []


class ExpectedIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> ExpectedIncome:
        return ExpectedIncome(**Handler.sanitize_api_dict(ExpectedIncome, data))

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
                objs_to_create = {}
                objs_to_update = {}
                postponed = []

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
                            "do_expect_a_income",
                        },
                    )

                    key = (item.cpr, item.year)
                    if key in objs_to_create:
                        # We have an item in this chunk already
                        # Current item will be handled in recursion
                        # This is done so that each postponed item
                        # will discover an existing DB object and
                        # update it (creating a history entry)
                        postponed.append(item)
                    else:
                        try:
                            # Find existing assessment
                            assessment = cls.get_person_year_assessment(
                                item.cpr, item.year, field_values["valid_from"]
                            )
                        except PersonYearAssessment.DoesNotExist:
                            # An existing assessment does not exist for this
                            # person and year and valid_from
                            objs_to_create[key] = PersonYearAssessment(
                                person_year=person_years[item.cpr],
                                load=load,
                                **field_values,
                            )
                        else:
                            # An assessment exists for this
                            # person and year and valid_from - update it.
                            changed = False
                            for name, value in field_values.items():
                                if getattr(assessment, name) != value:
                                    setattr(assessment, name, value)
                                    changed = True
                            if changed:
                                objs_to_update[key] = assessment

                objs_to_create_list = list(objs_to_create.values())
                objs_to_update_list = list(objs_to_update.values())

                bulk_create_with_history(objs_to_create_list, PersonYearAssessment)
                bulk_update_with_history(
                    objs_to_update_list,
                    PersonYearAssessment,
                    [
                        f.name
                        for f in PersonYearAssessment._meta.fields
                        if not f.primary_key
                    ],
                )

                out.write(
                    f"Created {len(objs_to_create_list)} PersonYearAssessment objects"
                )
                out.write(
                    f"Updated {len(objs_to_update_list)} PersonYearAssessment objects"
                )

                if postponed:
                    objs_to_update_list += cls.create_or_update_objects(
                        year, postponed, load, out
                    )

                return objs_to_create_list + objs_to_update_list

        # Fall-through: return empty list
        return []


class MonthlyIncomeHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> MonthlyIncome:
        return MonthlyIncome(**Handler.sanitize_api_dict(MonthlyIncome, data))

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
        objs_to_create = {}
        objs_to_update = {}
        postponed = []

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

                key = (item.cpr, item.year, item.month, item.cvr)
                if key in objs_to_create or key in objs_to_update:
                    # We have an item in this chunk already
                    # Current item will be handled in recursion
                    # This is done so that each postponed item
                    # will discover an existing DB object and
                    # update it (creating a history entry)
                    postponed.append(item)
                else:
                    try:
                        # Find existing monthly income report
                        report = MonthlyIncomeReport.objects.get(
                            person_month=person_month,
                            employer=employer,
                        )
                    except MonthlyIncomeReport.DoesNotExist:
                        # An existing monthly income report does not exist
                        # for this person, month and employer - create it.
                        report = MonthlyIncomeReport(
                            person_month=person_month,
                            load=load,
                            employer=employer,
                            **field_values,
                        )
                        report.update_amount()
                        objs_to_create[key] = report
                    else:
                        # An existing monthly income report exists
                        # for this person month and employer - update it.
                        changed = False
                        for name, value in field_values.items():
                            if getattr(report, name) != value:
                                setattr(report, name, value)
                                changed = True
                        if changed:
                            report.update_amount()
                            objs_to_update[key] = report
        objs_to_create_list = list(objs_to_create.values())
        objs_to_update_list = list(objs_to_update.values())

        bulk_create_with_history(
            objs_to_create_list,
            MonthlyIncomeReport,
        )
        bulk_update_with_history(
            objs_to_update_list,
            MonthlyIncomeReport,
            [f.name for f in MonthlyIncomeReport._meta.fields if not f.primary_key],
        )
        if postponed:
            objs_to_update_list += cls._create_or_update_monthly_income_reports(
                postponed, load
            )
        return objs_to_create_list + objs_to_update_list


class TaxInformationHandler(Handler):

    @staticmethod
    def from_api_dict(data: Dict[str, str | int | bool | float]) -> TaxInformation:
        return TaxInformation(**Handler.sanitize_api_dict(TaxInformation, data))

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
            )
            # TODO: Brug data i items til at populere databasen

    @classmethod
    def update_missing(cls, year: int, found_cprs: Iterable[str], load: DataLoad):
        # Update existing items in DB that are not in the input
        to_update = list(
            PersonYear.objects.filter(year__year=year).exclude(
                person__cpr__in=found_cprs
            )
        )
        for chunk in batched(to_update, 1000):
            for person_year_3 in chunk:
                person_year_3.load = load
                person_year_3.tax_scope = TaxScope.FORSVUNDET_FRA_MANDTAL
            bulk_update_with_history(
                chunk,
                PersonYear,
                fields=("load", "tax_scope"),
                batch_size=1000,
            )
