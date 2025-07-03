# SPDX-FileCopyrightText: 2023 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import Iterable, Tuple, Type

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from suila.models import (
    AnnualIncome,
    BTaxPayment,
    EboksMessage,
    Employer,
    IncomeEstimate,
    MonthlyIncomeReport,
    Note,
    NoteAttachment,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
    PersonYearEstimateSummary,
    PersonYearU1AAssessment,
    PrismeBatch,
    StandardWorkBenefitCalculationMethod,
    Year,
)


class Command(BaseCommand):
    help = "Creates groups"

    def get_permissions(self, *modelactions: Tuple[Type, Iterable[str]]):
        for model, actions in modelactions:
            content_type = ContentType.objects.get_for_model(
                model, for_concrete_model=False
            )
            for action in actions:
                codename = (
                    f"{action}_{content_type.model}"
                    if action in ("view", "change", "add", "delete")
                    else action
                )
                yield Permission.objects.get(
                    codename=codename,
                    content_type=content_type,
                )

    def set_group_permissions(self, group: Group, *permissions: Permission):
        for permission in permissions:
            group.permissions.add(permission)

    def handle(self, *args, **options):
        self.setup_borgerservice()
        self.setup_tax_officer()
        self.setup_rate_editor()

    def setup_borgerservice(self):
        borgerservice, _ = Group.objects.update_or_create(
            name="Borgerservice",
        )
        self.set_group_permissions(
            borgerservice,
            *self.get_permissions(
                (Year, ("view",)),
                (Person, ("view",)),
                (PersonYear, ("view",)),
                (PersonMonth, ("view",)),
                (Employer, ("view",)),
                (MonthlyIncomeReport, ("view",)),
                (BTaxPayment, ("view",)),
                (IncomeEstimate, ("view",)),
                (PersonYearEstimateSummary, ("view",)),
                (PersonYearAssessment, ("view",)),
                (AnnualIncome, ("view",)),
                (EboksMessage, ("view",)),
                (PersonYearU1AAssessment, ("view",)),
                (Note, ("view",)),
                (NoteAttachment, ("view",)),
            ),
        )

    def setup_tax_officer(self):
        tax, _ = Group.objects.update_or_create(name="Skattestyrelsen")
        self.set_group_permissions(
            tax,
            *self.get_permissions(
                (Year, ("view",)),
                (Person, ("view", "change")),
                (Person, ("view_data_analysis",)),
                (PersonYear, ("view", "change")),
                (PersonMonth, ("view",)),
                (Employer, ("view",)),
                (MonthlyIncomeReport, ("view",)),
                (BTaxPayment, ("view",)),
                (IncomeEstimate, ("view",)),
                (PersonYearEstimateSummary, ("view",)),
                (PersonYearAssessment, ("view",)),
                (AnnualIncome, ("view",)),
                (EboksMessage, ("view",)),
                (PersonYearU1AAssessment, ("view",)),
                (Note, ("view",)),
                (NoteAttachment, ("view",)),
                (
                    StandardWorkBenefitCalculationMethod,
                    ("use_adminsite_calculator_parameters",),
                ),
                (
                    PrismeBatch,
                    ("can_download_reports",),
                ),
            ),
        )

    def setup_rate_editor(self):
        editor, _ = Group.objects.update_or_create(name="Rateadministrator")
        self.set_group_permissions(
            editor,
            *self.get_permissions(
                (
                    StandardWorkBenefitCalculationMethod,
                    ("view", "add", "change", "delete"),
                ),
                (
                    Year,
                    ("view", "add", "change"),
                ),
            ),
        )
