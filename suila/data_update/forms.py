# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from django.forms import CharField, Form, ModelForm
from django.utils import timezone

from suila.models import (
    AnnualIncome,
    MonthlyIncomeReport,
    PersonMonth,
    PersonYear,
    PersonYearAssessment,
)


class ActionForm(Form):
    action = CharField()


class PersonYearCreateForm(ModelForm):
    class Meta:
        model = PersonYear
        fields = ("year",)

    def __init__(self, person, *args, **kwargs):
        self.person = person
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.person = self.person
        return super().save(commit)


class PersonMonthCreateForm(ModelForm):
    class Meta:
        model = PersonMonth
        fields = ("month",)

    def __init__(self, person_year, *args, **kwargs):
        self.person_year = person_year
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.person_year = self.person_year
        self.instance.import_date = timezone.now()
        return super().save(commit)


class AnnualIncomeForm(ModelForm):
    class Meta:
        model = AnnualIncome
        fields = (
            "salary",
            "public_assistance_income",
            "retirement_pension_income",
            "disability_pension_income",
            "ignored_benefits",
            "occupational_benefit",
            "foreign_pension_income",
            "subsidy_foreign_pension_income",
            "dis_gis_income",
            "other_a_income",
            "deposit_interest_income",
            "bond_interest_income",
            "other_interest_income",
            "education_support_income",
            "care_fee_income",
            "alimony_income",
            "foreign_dividend_income",
            "foreign_income",
            "free_journey_income",
            "group_life_income",
            "rental_income",
            "other_b_income",
            "free_board_income",
            "free_lodging_income",
            "free_housing_income",
            "free_phone_income",
            "free_car_income",
            "free_internet_income",
            "free_boat_income",
            "free_other_income",
            "pension_payment_income",
            "catch_sale_market_income",
            "catch_sale_factory_income",
            "account_tax_result",
            "account_share_business_amount",
            "shareholder_dividend_income",
        )


class AnnualIncomeCreateForm(AnnualIncomeForm):

    def __init__(self, person_year, *args, **kwargs):
        self.person_year = person_year
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.person_year = self.person_year
        return super().save(commit)


class PersonYearAssessmentForm(ModelForm):
    class Meta:
        model = PersonYearAssessment
        fields = (
            "valid_from",
            "capital_income",
            "education_support_income",
            "care_fee_income",
            "alimony_income",
            "other_b_income",
            "gross_business_income",
            "benefits_income",
            "business_turnover",
            "catch_sale_factory_income",
            "catch_sale_market_income",
            "goods_comsumption",
            "operating_costs_catch_sale",
            "operating_expenses_own_company",
            "tax_depreciation",
            "bussiness_interest_income",
            "bussiness_interest_expenses",
            "extraordinary_bussiness_income",
            "extraordinary_bussiness_expenses",
        )


class PersonYearAssessmentCreateForm(PersonYearAssessmentForm):

    def __init__(self, person_year, *args, **kwargs):
        self.person_year = person_year
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.person_year = self.person_year
        return super().save(commit)


class MonthlyIncomeForm(ModelForm):
    class Meta:
        model = MonthlyIncomeReport
        fields = (
            "salary_income",
            "catchsale_income",
            "public_assistance_income",
            "alimony_income",
            "dis_gis_income",
            "retirement_pension_income",
            "disability_pension_income",
            "ignored_benefits_income",
            "employer_paid_gl_pension_income",
            "foreign_pension_income",
            "civil_servant_pension_income",
            "other_pension_income",
            "capital_income",
        )


class MonthlyIncomeCreateForm(MonthlyIncomeForm):

    def __init__(self, person_month, *args, **kwargs):
        self.person_month = person_month
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.person_month = self.person_month
        return super().save(commit)
