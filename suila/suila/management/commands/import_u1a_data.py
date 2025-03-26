# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from suila.integrations.akap.u1a import (
    AKAPU1AItem,
    get_akap_u1a_items,
    get_akap_u1a_items_unique_cprs,
)
from suila.management.commands.common import SuilaBaseCommand
from suila.models import (
    DataLoad,
    Employer,
    MonthlyIncomeReport,
    Person,
    PersonMonth,
    PersonYear,
    Year,
)


class ImportResult(BaseModel):
    import_year: int
    cprs_handled: List[str] = []
    cprs_skipped: List[str] = []

    employers_created: List[int] = []
    person_years_created: List[int] = []
    person_months_created: List[int] = []
    person_months_updated: List[int] = []
    monthly_income_reports_created: List[int] = []
    monthly_income_reports_updated: List[int] = []


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    def _write_verbose(self, message: str):
        if self._verbose:
            self.stdout.write(message)

    @transaction.atomic
    def _handle(self, *args, **kwargs):
        self._verbose = kwargs["verbosity"] > 1
        dry = kwargs.get("dry", False)
        year = kwargs.get("year", None)
        cpr = kwargs.get("cpr", None)

        # Configure years
        if year is None:
            years = Year.objects.all().order_by("year")
        else:
            fetched_year, _ = Year.objects.get_or_create(year=year)
            years = [fetched_year]

        # Create a DataLoad object for this import
        data_load: DataLoad = DataLoad.objects.create(
            source="api",
            parameters={"host": settings.AKAP_HOST, "name": "AKAP udbytte U1A API"},
        )

        # Output of the process about to
        self._write_verbose("Running AKAP U1A data import:")
        self._write_verbose(f"- Host: {settings.AKAP_HOST}")
        self._write_verbose(f"- year(s): {[y.year for y in years]}")
        self._write_verbose(f"- CPR: {cpr}")
        self._write_verbose(f"- DataLoad: {data_load.id}\n\n")

        # Import data for each year
        results: List[ImportResult] = []
        for year in years:
            self.stdout.write(f"Importing: U1A entries for year {year} (CPR={cpr})")
            try:
                results.append(self._import_data(data_load, year, cpr))
            except Exception as e:
                raise e

        # Rollback everything if DRY-run is used
        if dry:
            transaction.set_rollback(True)
            self.stdout.write("Dry run complete. All changes rolled back.")

        # Finish
        self.stdout.write("-------------------- REPORT --------------------")
        for idx, result in enumerate(results):
            self.stdout.write(f"Year: {result.import_year}")
            self.stdout.write(
                (
                    "CPRs handled/skipped: "
                    f"{len(result.cprs_handled)}/{len(result.cprs_skipped)}"
                )
            )

            self.stdout.write(f"Employers created: {len(result.employers_created)}")
            self.stdout.write(
                f"PersonYears created: {len(result.person_years_created)}"
            )

            self.stdout.write(
                f"PersonMonths created: {len(result.person_months_created)}"
            )
            self.stdout.write(
                f"PersonMonths updated: {len(result.person_months_updated)}"
            )

            self.stdout.write(
                (
                    "MonthlyIncomeReports created: "
                    f"{len(result.monthly_income_reports_created)}"
                )
            )
            self.stdout.write(
                (
                    "MonthlyIncomeReports updated: "
                    f"{len(result.monthly_income_reports_updated)}"
                )
            )

            if idx < len(results) - 1:
                self.stdout.write("")

        self.stdout.write("------------------------------------------------")
        self.stdout.write("DONE!")

    def _import_data(
        self,
        data_load: DataLoad,
        year: Year,
        cpr: Optional[str] = None,
    ) -> ImportResult:
        result = ImportResult(import_year=year.year)

        u1a_cprs: List[str] = [cpr] if cpr else []
        if len(u1a_cprs) == 0:
            # Get all unique CPRs in that year from AKAP
            self._write_verbose(f"- No CPR(s) specified, fetching all for year: {year}")
            u1a_cprs = get_akap_u1a_items_unique_cprs(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year.year,
                fetch_all=True,
            )

            if len(u1a_cprs) > 0:
                self._write_verbose(f"- Fetched CPRs: {u1a_cprs}")

        if len(u1a_cprs) < 1:
            self.stdout.write("- No CPR numbers found.")
            self.stdout.write("Stopping import!")
            return result

        # Get Person objects for the CPR
        self._write_verbose(f"- Fetching persons from CPRs: {u1a_cprs}")
        persons_qs = Person.objects.filter(cpr__in=u1a_cprs)
        persons_map = {p.cpr: p for p in persons_qs}

        persons: List[Person] = []
        for cpr in u1a_cprs:
            person = persons_map.get(cpr)
            if person:
                persons.append(person)
            else:
                result.cprs_skipped.append(cpr)
                self.stdout.write(
                    f"- WARNING: Could not find Person with CPR: {cpr}, skipping!"
                )

        if not persons:
            self.stdout.write("- Unable to find Persons from CPR(s).")
            self.stdout.write("Stopping import!")
            return result

        # Go through each person and create/update MonthlyIncomeReports
        reports_to_create = {}
        reports_to_update = {}
        person_months_to_update: Dict[int, PersonMonth] = {}

        for person in persons:
            self.stdout.write(
                f"- Fetching AKAP U1A data for person: {person} ({person.cpr})..."
            )
            person_akap_u1a_items = get_akap_u1a_items(
                settings.AKAP_HOST,  # type: ignore[misc]
                settings.AKAP_API_SECRET,  # type: ignore[misc]
                year=year.year,
                cpr=person.cpr,
                fetch_all=True,
            )
            self._write_verbose(f"\t- Fetched U1A-items: {len(person_akap_u1a_items)}")

            if len(person_akap_u1a_items) < 1:
                self._write_verbose(
                    f"\t- Person, {person}, does not have any U1AItems.. Skipping!"
                )
                result.cprs_skipped.append(person.cpr)
                continue

            u1a_items_dict: Dict[int, List[AKAPU1AItem]] = defaultdict(list)
            for item in person_akap_u1a_items:
                u1a_items_dict[item.u1a.id].append(item)

            # Get, or create, PersonYear
            self._write_verbose(f"\t- Fetching/creating PersonYear: {year}")
            person_year, created = PersonYear.objects.get_or_create(
                person=person,
                year=year,
                defaults={"load": data_load},
            )

            if created:
                result.person_years_created.append(person_year.id)

            # Update, or create, MonthlyIncomeReports for each U1A
            for _, u1a_items in u1a_items_dict.items():
                u1a = u1a_items[0].u1a
                u1a_month = u1a.dato_vedtagelse.month

                self.stdout.write(f"\t- Handling data for U1A: {u1a}...")

                # Get U1A Employer & PersonMonth (or create them)
                self._write_verbose(
                    (
                        "\t\t- Fetching/creating Employer: "
                        f"{u1a.virksomhedsnavn} ({u1a.cvr})"
                    )
                )
                u1a_employer, created = Employer.objects.get_or_create(
                    cvr=u1a.cvr,
                    defaults={"load": data_load, "name": u1a.virksomhedsnavn},
                )
                if created:
                    result.employers_created.append(u1a_employer.id)

                self._write_verbose(
                    (
                        "\t\t- Fetching/creating PersonMonth: "
                        f"{person_year.year.year}/{u1a_month}"
                    )
                )
                u1a_person_month, created = PersonMonth.objects.get_or_create(
                    person_year=person_year,
                    month=u1a_month,
                    defaults={"load": data_load, "import_date": data_load.timestamp},
                )
                if created:
                    result.person_months_created.append(u1a_person_month.id)

                # Reset existing MonthlyIncomeReport, with U-income,
                # and update related PersonMonth.amount_sum
                self._write_verbose(
                    (
                        "\t\t- Resetting MonthlyIncomeReports with u_income for "
                        f"PersonMonth: {u1a_person_month} ({u1a_employer})"
                    )
                )
                existing_u1a_reports = MonthlyIncomeReport.objects.filter(
                    employer=u1a_employer,
                    person_month=u1a_person_month,
                    u_income__gt=Decimal(0),
                )

                if len(existing_u1a_reports) > 0:
                    for existing_report in existing_u1a_reports:
                        existing_report.u_income = Decimal("0.00")
                        existing_report.update_amount()
                        existing_report.save()

                    self._write_verbose(
                        (
                            "\t\t\t- Removed U-income from "
                            f"{len(existing_u1a_reports)} existing "
                            "MonthlyIncomeReport(s)"
                        )
                    )

                # Add U-income to MonthlyIncomeReport (or create it)
                self.stdout.write(
                    (
                        "\t\t- Updating MonthlyIncomeReports for PersonMonth: "
                        f"{u1a_person_month} ({u1a_employer})..."
                    )
                )

                field_values: Dict[str, Any] = {
                    "u_income": sum(
                        (u1a_item.udbytte for u1a_item in u1a_items), Decimal("0")
                    )
                }
                key = (
                    person.cpr,
                    person_year.year.year,
                    u1a_person_month.month,
                    u1a.cvr,
                )
                self._write_verbose(f"\t\t\t- MonthlyIncomeReport key: {key}")

                try:
                    report = MonthlyIncomeReport.objects.get(
                        employer=u1a_employer,
                        person_month=u1a_person_month,
                    )
                except MonthlyIncomeReport.DoesNotExist:
                    report = MonthlyIncomeReport(
                        employer=u1a_employer,
                        person_month=u1a_person_month,
                        load=data_load,
                        **field_values,
                    )
                    report.update_amount()
                    reports_to_create[key] = report
                    self._write_verbose(
                        f"\t\t\t- CREATED MonthlyIncomeReport: {report}"
                    )
                else:
                    # An existing monthly income report exists
                    # for this person month and employer - update it.
                    changed = False
                    for field_name, field_value in field_values.items():
                        if getattr(report, field_name) != field_value:
                            setattr(report, field_name, field_value)
                            changed = True

                    if changed:
                        report.update_amount()
                        reports_to_update[key] = report
                        self._write_verbose(
                            f"\t\t\t- UPDATED MonthlyIncomeReport: {report}"
                        )

                # Lastly, set the related PersonMonth model to be updated
                # NOTE: This will occur after MonthlyIncomeReports have been created,
                # or updated.
                person_months_to_update[u1a_person_month.id] = u1a_person_month

            result.cprs_handled.append(person.cpr)

        self.stdout.write("- Comitting database changes...")

        # Create & update models with history & in bulk
        reports_to_create_list = list(reports_to_create.values())
        created_reports = bulk_create_with_history(
            reports_to_create_list,
            MonthlyIncomeReport,
        )
        result.monthly_income_reports_created = [
            report.id for report in created_reports
        ]
        self._write_verbose(
            (
                "\t- (Database) MonthlyIncomeReport created: "
                f"{len(result.monthly_income_reports_created)}"
            )
        )

        reports_to_update_list = list(reports_to_update.values())
        bulk_update_with_history(
            reports_to_update_list,
            MonthlyIncomeReport,
            [f.name for f in MonthlyIncomeReport._meta.fields if not f.primary_key],
        )
        result.monthly_income_reports_updated = [
            report.id for report in reports_to_update_list
        ]
        self._write_verbose(
            (
                "\t- (Database) MonthlyIncomeReport updated: "
                f"{len(result.monthly_income_reports_updated)}"
            )
        )

        # Final, update PersonMonth.amount_sums
        # NOTE: This can only occur after create/update of MonthlyIncomeReports,
        # since ."update_amount_sum()" uses a MonthlyIncomeReports-queryset.
        self.stdout.write(
            (
                "- Updating existing PersonMonths, "
                f"{len(person_months_to_update.keys())}, after MonthlyIncomeReport "
                "changes..."
            )
        )
        for pm in list(person_months_to_update.values()):
            pm.update_amount_sum()
            pm.save()

            if pm.id not in result.person_months_created:
                result.person_months_updated.append(pm.id)

        return result
