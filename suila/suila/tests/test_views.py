# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from common.models import PageView, User
from common.tests.test_mixins import TestViewMixin
from common.view_mixins import ViewLogMixin
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.files.temp import NamedTemporaryFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.template.response import TemplateResponse
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.test.testcases import SimpleTestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import ContextMixin, TemplateView, View
from django_otp.util import random_hex
from requests import Response

from suila.forms import NoteAttachmentFormSet
from suila.models import (
    BTaxPayment,
    Employer,
    MonthlyIncomeReport,
    Note,
    NoteAttachment,
    Person,
    PersonMonth,
    PersonYear,
    PersonYearU1AAssessment,
    StandardWorkBenefitCalculationMethod,
    SuilaEboksMessage,
    Year,
)
from suila.view_mixins import PermissionsRequiredMixin
from suila.views import (
    CalculatorView,
    CPRField,
    EboksMessageView,
    GeneratedEboksMessageView,
    IncomeSignal,
    IncomeSignalTable,
    IncomeSignalType,
    IncomeSumsBySignalTypeTable,
    PersonDetailEboksPreView,
    PersonDetailEboksSendView,
    PersonDetailIncomeView,
    PersonDetailNotesAttachmentView,
    PersonDetailNotesView,
    PersonDetailView,
    PersonFilterSet,
    PersonGraphView,
    PersonMonthTable,
    PersonSearchView,
    PersonTable,
    PersonYearPauseUpdateView,
    RootView,
    YearMonthMixin,
)


class TestRootView(TestViewMixin, TestCase):

    view_class = RootView

    def test_view_log(self):
        self.request_get(self.admin_user, "/")
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "RootView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {})
        self.assertEqual(pageview.params, {})
        self.assertEqual(pageview.itemviews.count(), 0)

    def test_2fa_not_set(self):
        view, response = self.request_get(self.admin_user, "/")
        response.render()
        self.assertFalse(view.get_context_data()["user_twofactor_enabled"])
        self.assertIsNotNone(
            BeautifulSoup(response.content, features="lxml").find(
                href=reverse("login:two_factor_setup")
            )
        )

    def test_2fa_set(self):
        self.admin_user.totpdevice_set.create(name="default", key=random_hex())
        view, response = self.request_get(self.admin_user, "/")
        response.render()
        self.assertTrue(view.get_context_data()["user_twofactor_enabled"])
        self.assertIsNone(
            BeautifulSoup(response.content, features="lxml").find(
                href=reverse("login:two_factor_setup")
            )
        )


class PersonEnv(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Add persons
        cls.person1, _ = Person.objects.update_or_create(
            cpr="0101011111", location_code=1
        )
        cls.person2, _ = Person.objects.update_or_create(
            cpr="0101012222", location_code=1
        )
        cls.person3, _ = Person.objects.update_or_create(
            cpr="0101013333", location_code=None
        )

        # Set up calculation method and year
        calc = StandardWorkBenefitCalculationMethod.objects.create(
            benefit_rate_percent=Decimal("17.5"),
            personal_allowance=Decimal("58000.00"),
            standard_allowance=Decimal("10000"),
            max_benefit=Decimal("15750.00"),
            scaledown_rate_percent=Decimal("6.3"),
            scaledown_ceiling=Decimal("250000.00"),
        )
        for year in range(2020, date.today().year + 1):
            Year.objects.update_or_create(
                year=year, defaults={"calculation_method": calc}
            )

        # Add "signal" data to person 1
        cls.person_year, _ = PersonYear.objects.update_or_create(
            person=cls.person1,
            year=Year.objects.get(year=2020),
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        # Create 12 PersonMonth objects, where each month amount is equal to the month
        # number.
        person_months = [
            PersonMonth(
                person_year=cls.person_year,
                month=i,
                benefit_paid=i,
                import_date=date(2020, 1, 1),
            )
            for i in range(1, 13)
        ]
        PersonMonth.objects.bulk_create(person_months)
        # Create `MonthlyIncomeReport` objects (3 sets of 12 months)
        employer1, _ = Employer.objects.update_or_create(name="Employer 1", cvr=1)
        employer2, _ = Employer.objects.update_or_create(name=None, cvr=2)
        income_reports = []
        for employer in (employer1, employer2, None):
            for person_month in person_months:
                income_report = MonthlyIncomeReport(
                    person_month=person_month,
                    employer=employer,
                    salary_income=(
                        person_month.benefit_paid * 10
                        if person_month.month > 1
                        else Decimal("0")
                    ),
                    catchsale_income=(
                        person_month.benefit_paid * 10
                        if person_month.month > 1
                        else Decimal("0")
                    ),
                )
                income_report.update_amount()
                income_reports.append(income_report)
        MonthlyIncomeReport.objects.bulk_create(income_reports)
        # Create `BTaxPayment` objects
        b_tax_payments = [
            BTaxPayment(
                person_month=person_month,
                amount_paid=(
                    person_month.benefit_paid * 10
                    if person_month.month > 1
                    else Decimal("0")
                ),
                # Provide values for non-nullable fields (unused in test)
                amount_charged=person_month.benefit_paid * 10,
                date_charged=person_month.year_month,
                rate_number=person_month.month,
                filename="",
                serial_number=0,
            )
            for person_month in person_months
        ]
        BTaxPayment.objects.bulk_create(b_tax_payments)
        # Create `PersonYearU1AAssessment` objects
        u1a_assessments = [
            PersonYearU1AAssessment(
                person_year=person_months[0].person_year, dividend_total=dividend_total
            )
            for dividend_total in (Decimal("0"), Decimal("10"))
        ]
        PersonYearU1AAssessment.objects.bulk_create(u1a_assessments)


class TimeContextMixin(TestViewMixin):
    def _time_context(self, year: int = 2020, month: int = 12):
        return patch("suila.views.timezone.now", return_value=datetime(year, month, 1))

    def _get_context_data(self, **params: Any):
        with self._time_context():
            view, response = self.request_get(self.admin_user, "", **params)
            return view.get_context_data()

    def view(self, user: User = None, path: str = "", **params: Any) -> TemplateView:
        with self._time_context():
            return super().view(user, path, **params)


class TestCPRField(SimpleTestCase):
    def test_accepts_cpr_variations(self):
        instance = CPRField()
        for variation in ("0101012222", "010101-2222"):
            with self.subTest(variation):
                self.assertEqual(instance.clean(variation), "0101012222")


class TestPersonSearchView(TimeContextMixin, PersonEnv):
    view_class = PersonSearchView

    def test_get_queryset_includes_padded_cpr(self):
        view = self.view(self.admin_user, "")
        self.assertQuerySetEqual(
            view.get_queryset(),
            [person.cpr.zfill(10) for person in Person.objects.all().order_by("cpr")],
            transform=lambda obj: obj._cpr,
        )

    def test_get_context_data_includes_person_table(self):
        with self._time_context(year=2020):
            view, response = self.request_get(self.admin_user)
            context = view.get_context_data()
            self.assertIn("table", context)
            self.assertIsInstance(context["table"], PersonTable)

    def test_get_context_data_includes_filterset(self):
        with self._time_context(year=2020):
            view, response = self.request_get(self.admin_user)
            self.assertIn("filter", response.context_data)
            self.assertIsInstance(response.context_data["filter"], PersonFilterSet)

    def test_borger_see_only_self(self):
        with self._time_context(year=2020):
            view, response = self.request_get(self.normal_user)
        qs = view.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.person1)

    def test_staff_see_all(self):
        view, response = self.request_get(self.staff_user)
        qs = view.get_queryset()
        self.assertEqual(qs.count(), 3)
        self.assertEqual(qs[0], self.person1)
        self.assertEqual(qs[1], self.person2)
        self.assertEqual(qs[2], self.person3)

    def test_other_see_none(self):
        view, response = self.request_get(self.other_user)
        self.assertEqual(view.get_queryset().count(), 0)

    def test_anonymous_see_none(self):
        view = self.view(self.no_user)
        self.assertEqual(view.get_queryset().count(), 0)

    def test_view_log(self):
        self.request_get(self.admin_user, "/persons/")
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonSearchView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {})
        self.assertEqual(pageview.params, {})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 3)
        self.assertEqual(
            {itemview.item for itemview in itemviews},
            {self.person1, self.person2, self.person3},
        )


class TestYearMonthMixin(TimeContextMixin, TestCase):
    class ImplView(YearMonthMixin, ContextMixin, View):
        """View implementation to use in tests"""

    request_factory = RequestFactory()

    def test_year_and_month_property_defaults(self):
        view = self._use_defaults()
        with self._time_context():
            self.assertEqual(view.year, 2020)
            self.assertEqual(view.month, 12)

    def test_year_and_month_query_parameters(self):
        # Act: 1. Test query parameters usage when year is current year
        with self._time_context(year=2020, month=6):
            view = self._use_query_parameters(2020, 1)
            self.assertEqual(view.year, 2020)
            # When `year` is current year, use the `month` provided in query params
            self.assertEqual(view.month, 1)

        # Act: 2. Test query parameters usage when year is before current year
        with self._time_context(year=2020, month=6):
            view = self._use_query_parameters(2019, 1)
            self.assertEqual(view.year, 2019)
            # When `year` is before current year, always use the last month of the year
            self.assertEqual(view.month, 12)

    def test_context_data_includes_year_and_month(self):
        view = self._use_defaults()
        with self._time_context(year=2020, month=12):
            context_data = view.get_context_data()
            self.assertEqual(context_data["year"], 2020)
            self.assertEqual(context_data["month"], 12)

    def _use_defaults(self) -> ImplView:
        view = self.ImplView()
        view.setup(self.request_factory.get(""))
        return view

    def _use_query_parameters(self, year: int, month: int) -> ImplView:
        view = self.ImplView()
        view.setup(
            self.request_factory.get("", data={"year": year, "month": month}),
            pk=0,
        )
        return view


class TestPersonDetailView(TimeContextMixin, PersonEnv):
    view_class = PersonDetailView

    def test_get_context_data(self):
        with self._time_context(year=2020):  # December 2020
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            # Verify that expected context variables are present
            self.assertIn("next_payout_date", response.context_data)
            self.assertIn("benefit_paid", response.context_data)
            self.assertIn("estimated_year_benefit", response.context_data)
            self.assertIn("estimated_year_result", response.context_data)
            self.assertIn("table", response.context_data)
            # Verify the values of the context variables
            self.assertIsNotNone(response.context_data["next_payout_date"])
            # When looking at page in December 2020, the "focus date" is October 2020
            # The mocked `benefit_paid` for October is 10 (= the month number.)
            self.assertEqual(response.context_data["benefit_paid"], Decimal("10.0"))
            self.assertIsNone(response.context_data["estimated_year_benefit"])
            self.assertEqual(response.context_data["estimated_year_result"], Decimal(0))
            self.assertIsInstance(response.context_data["table"], PersonMonthTable)
            self.assertFalse(response.context_data["table"].orderable)

    def test_get_context_data_handles_no_matching_person_month(self):
        # Arrange: go to year without `PersonMonth` objects for `normal_user`
        PersonYear.objects.update_or_create(
            person=self.person1,
            year=Year.objects.get(year=2021),
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        with self._time_context(year=2021):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            self.assertFalse(response.context_data["show_next_payment"])

    def test_get_context_data_calculates_next_payout_date(self):
        # Arrange: add person month for person 1 in January 2025
        person_year, _ = PersonYear.objects.get_or_create(
            person=self.person1,
            year=Year.objects.get(year=2025),
        )
        PersonMonth.objects.create(
            person_year=person_year, month=1, import_date=date.today()
        )
        with self._time_context(year=2025, month=3):  # March 2025
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            self.assertEqual(
                response.context_data["next_payout_date"], date(2025, 3, 18)
            )

    def test_get_table_data(self):
        with self._time_context(year=2020):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            queryset = view.get_table_data()
            self.assertQuerySetEqual(
                queryset,
                range(1, 13),
                transform=lambda obj: obj.month,
                ordered=True,
            )

    def test_borger_see_only_self(self):
        with self._time_context(year=2020):
            self.request_get(self.normal_user, pk=self.person1.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person2.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person3.pk)

    def test_other_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.other_user, pk=self.person1.pk)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", pk=self.person1.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person2.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person3.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/?year=2020",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.person1)

    def test_no_personyears(self):
        view, response = self.request_get(
            self.admin_user,
            f"/persons/{self.person2.pk}/?year=2020",
            pk=self.person2.pk,
        )
        self.assertEqual(view.get_template_names(), ["suila/person_no_year.html"])

        self.person1.personyear_set.all().delete()
        view, response = self.request_get(
            self.normal_user,
            f"/persons/{self.person1.pk}/?year=2020",
            pk=self.person1.pk,
        )
        self.assertEqual(view.get_template_names(), ["suila/person_no_year.html"])


class TestPersonDetailIncomeView(TimeContextMixin, PersonEnv):
    maxDiff = None

    view_class = PersonDetailIncomeView

    def test_get_context_data(self):
        with self._time_context(year=2020):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            # Verify that expected context variables are present
            self.assertIn("sum_table", response.context_data)
            self.assertIn("detail_table", response.context_data)
            self.assertIn("available_person_years", response.context_data)
            # Verify the values of the context variables
            self.assertIsInstance(
                response.context_data["sum_table"], IncomeSumsBySignalTypeTable
            )
            self.assertIsInstance(
                response.context_data["detail_table"], IncomeSignalTable
            )
            self.assertQuerySetEqual(
                response.context_data["available_person_years"],
                [self.person_year],
            )
            self.assertEqual(response.context_data["sum_table"].month, 12)

    def test_no_personyear(self):
        with self._time_context(year=2021), self.assertRaises(Http404):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)

    def test_get_context_data_sum_table_for_january(self):
        # Even if there are income signals in December (which there are in this test),
        # the sum table should consider the current calendar month to be the latest
        # displayable month for the `current_month_sum` column.
        with self._time_context(year=2020, month=1):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            self.assertEqual(response.context_data["sum_table"].month, 1)

    def test_get_context_data_no_data(self):
        PersonYear.objects.update_or_create(
            person=self.person1,
            year=Year.objects.get(year=2021),
            preferred_estimation_engine_a="InYearExtrapolationEngine",
        )
        with self._time_context(year=2021):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            self.assertIsInstance(
                response.context_data["sum_table"], IncomeSumsBySignalTypeTable
            )
            # The sum table should contain lines for each signal type, where both the
            # monthly and the yearly sums are zero for all lines.
            self.assertEqual(
                len(response.context_data["sum_table"].data), len(IncomeSignalType)
            )
            self.assertListEqual(
                [
                    (item["current_month_sum"], item["current_year_sum"])
                    for item in response.context_data["sum_table"].data
                ],
                [(Decimal("0"), Decimal("0"))]
                * len(response.context_data["sum_table"].data),
            )

    def test_get_income_signals(self):
        with self._time_context(year=2020):
            # Act
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            result = view.get_income_signals()
            # Assert: monthly income signals are as expected
            self.assertListEqual(
                [
                    signal
                    for signal in result
                    if signal.signal_type
                    in (IncomeSignalType.Lønindkomst, IncomeSignalType.Indhandling)
                ],
                [
                    IncomeSignal(
                        signal_type,
                        employer,
                        Decimal(month * 10),
                        date(2020, month, 1),
                    )
                    for month, signal_type, employer in itertools.product(
                        # 11 months in reverse order (January is exempt due to zero
                        # income.)
                        range(12, 1, -1),
                        # Two types of signal
                        (IncomeSignalType.Lønindkomst, IncomeSignalType.Indhandling),
                        # 12 entries for employer 2 (who only has a CVR, no name),
                        # 12 entries for employer 1 (whose name is "Employer 1"),
                        # 12 entries without employer ("Ikke oplyst".)
                        # Sorted alphabetically.
                        (
                            _("CVR: %(cvr)s") % {"cvr": 2},
                            "Employer 1",
                            _("Ikke oplyst"),
                        ),
                    )
                ],
            )
            # Assert: B tax payment signals are as expected
            self.assertListEqual(
                [
                    signal
                    for signal in result
                    if signal.signal_type == IncomeSignalType.BetaltBSkat
                ],
                [
                    IncomeSignal(
                        IncomeSignalType.BetaltBSkat,
                        _("Rate: %(rate_number)s") % {"rate_number": month},
                        Decimal(month * 10),
                        date(2020, month, 1),
                    )
                    # 11 months in reverse order (January is exempt due to zero income)
                    for month in range(12, 1, -1)
                ],
            )
            # Assert: U1A signals are as expected
            self.assertListEqual(
                [
                    signal
                    for signal in result
                    if signal.signal_type == IncomeSignalType.Udbytte
                ],
                [
                    IncomeSignal(
                        IncomeSignalType.Udbytte,
                        "",
                        Decimal("10"),
                        date.today(),
                    )
                ],
            )

    def test_source_query_parameter(self):
        with self._time_context(year=2020):
            # Act: perform GET request with `source` parameter set to valid value
            request = self.request_factory.get(
                "", data={"source": quote_plus("Employer 1")}
            )
            request.user = self.normal_user
            view = self.view_class()
            view.setup(request, pk=self.person1.pk)
            response = view.get(request, pk=self.person1.pk)
            # Assert: only signals matching the `source` parameter are displayed in the
            # detail table.
            filtered_signals = response.context_data["detail_table"].data.data
            self.assertEqual(
                [signal.source for signal in filtered_signals],
                ["Employer 1"] * len(filtered_signals),
            )

    def test_borger_see_only_self(self):
        with self._time_context(year=2020):
            self.request_get(self.normal_user, pk=self.person1.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person2.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person3.pk)

    def test_other_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.other_user, pk=self.person1.pk)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", pk=self.person1.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person2.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person3.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/income/?year=2020",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailIncomeView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.person1)


class TestIncomeSumsBySignalTypeTable(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.instance = IncomeSumsBySignalTypeTable([], 2025, 3)

    def test_month_column_name(self):
        # Arrange: ensure Danish locale is used
        translation.activate("da")
        # Act: call `before_render` with (irrelevant) `request` arg
        self.instance.before_render(None)
        # Assert
        self.assertEqual(
            self.instance.columns["current_month_sum"].column.verbose_name,
            "Marts 2025",
        )


class TestPersonGraphView(TimeContextMixin, PersonEnv):
    view_class = PersonGraphView

    def test_get_context_data_for_present_person_month(self):
        # Arrange: create `PersonMonth` with estimated year result (used as input for
        # calculating yearly benefit.)
        PersonMonth.objects.update_or_create(
            person_year=self.person_year,
            month=1,
            defaults={
                "estimated_year_result": Decimal("288000"),
                "import_date": date.today(),
            },
        )
        with self._time_context(year=2020, month=1):
            # Act
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            # Assert
            self.assertEqual(response.context_data["yearly_income"], "288000.00")
            self.assertEqual(response.context_data["yearly_benefit"], "13356")

    def test_get_context_data_for_not_present_person_month(self):
        # Arrange: request graph for year where no person months are available
        with self._time_context(year=2021):
            # Act
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            # Assert
            self.assertNotIn("yearly_income", response.context_data)
            self.assertNotIn("yearly_benefit", response.context_data)

    # The tests below are copied from `TestPersonDetailView`

    def test_borger_see_only_self(self):
        with self._time_context(year=2020):
            self.request_get(self.normal_user, pk=self.person1.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person2.pk)
            with self.assertRaises(PermissionDenied):
                self.request_get(self.normal_user, pk=self.person3.pk)

    def test_other_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.request_get(self.other_user, pk=self.person1.pk)

    def test_view_anonymous_denied(self):
        view, response = self.request_get(self.no_user, "", pk=self.person1.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person2.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")
        view, response = self.request_get(self.no_user, "", pk=self.person3.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login?next=/")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/graph/?year=2020",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonGraphView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.person1)


class TestNoteView(TimeContextMixin, PersonEnv):
    view_class = PersonDetailNotesView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create(username="TestUser")

    def tearDown(self):
        # Clean up notes & files saved to disk
        note = Note.objects.filter(personyear=self.person_year).first()
        if note:
            for attachment in note.attachments.all():
                if attachment.file:
                    file_path = attachment.file.name
                    if default_storage.exists(file_path):
                        default_storage.delete(file_path)
        Note.objects.filter(personyear=self.person_year).delete()

        super().tearDown()

    def test_get_formset(self):
        view = self.view_class()
        request = self.request_factory.get("")
        request.user = self.admin_user
        view.setup(request, pk=self.person1.pk)
        response = view.get(request, pk=self.person1.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(view.get_formset(), NoteAttachmentFormSet))
        self.assertTrue(
            isinstance(view.get_formset(NoteAttachmentFormSet), NoteAttachmentFormSet)
        )
        self.assertTrue(
            isinstance(view.get_context_data()["formset"], NoteAttachmentFormSet)
        )
        self.assertTrue(
            isinstance(
                view.get_context_data(formset=view.get_formset())["formset"],
                NoteAttachmentFormSet,
            )
        )

    def test_get_kwargs(self):
        view = self.view_class()
        for request in (self.request_factory.post(""), self.request_factory.put("")):
            view.setup(request, pk=self.person1.pk)
            self.assertTrue("data" in view.get_formset_kwargs())
            self.assertTrue("files" in view.get_formset_kwargs())
        for request in (self.request_factory.get(""), self.request_factory.head("")):
            view.setup(request, pk=self.person1.pk)
            self.assertFalse("data" in view.get_formset_kwargs())
            self.assertFalse("files" in view.get_formset_kwargs())

    def test_create_simple(self):
        view = self.view_class()
        request = self.request_factory.post(
            reverse("suila:person_detail_notes", kwargs={"pk": self.person1.pk}),
            {
                "text": "Test tekst",
                "attachments-TOTAL_FORMS": 0,
                "attachments-INITIAL_FORMS": 0,
                "attachments-MIN_NUM_FORMS": 0,
                "attachments-MAX_NUM_FORMS": 1000,
            },
            format="multipart",
        )
        request.user = self.admin_user
        view.setup(request, pk=self.person1.pk)
        with self._time_context():
            response = view.post(request, pk=self.person1.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(view.get_context_data()["form"].errors, {})
        qs = Note.objects.filter(personyear=self.person_year)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(list(view.get_context_data()["notes"]), list(qs))
        self.assertEqual(qs.first().text, "Test tekst")

    def test_create_attachment(self):
        view = self.view_class()
        request = self.request_factory.post(
            reverse("suila:person_detail_notes", kwargs={"pk": self.person1.pk}),
            {
                "text": "Test tekst",
                "attachments-TOTAL_FORMS": 3,
                "attachments-INITIAL_FORMS": 0,
                "attachments-MIN_NUM_FORMS": 0,
                "attachments-MAX_NUM_FORMS": 1000,
                "attachments-0-file": SimpleUploadedFile(
                    name="testfile",
                    content=b"Test data",
                    content_type="text/plain",
                ),
                "attachments-1-file": SimpleUploadedFile(
                    name="testfile2",
                    content=b"Test data 2",
                    content_type="text/plain",
                ),
            },
            format="multipart",
        )
        request.user = self.admin_user
        view.setup(request, pk=self.person1.pk)
        with self._time_context():
            view.post(request, pk=self.person1.pk)
        self.assertEqual(view.get_context_data()["form"].errors, {})
        qs = Note.objects.filter(personyear=self.person_year)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(list(view.get_context_data()["notes"]), list(qs))
        note = qs.first()
        self.assertEqual(note.text, "Test tekst")
        self.assertEqual(note.attachments.count(), 2)

        attachments = list(note.attachments.all())
        attachment = attachments[0]
        self.assertEqual(attachment.content_type, "text/plain")
        self.assertEqual(attachment.filename, "testfile")
        with attachment.file.open() as f:
            data = f.read()
        self.assertEqual(data, b"Test data")

        attachment = attachments[1]
        self.assertEqual(attachment.content_type, "text/plain")
        self.assertEqual(attachment.filename, "testfile2")
        with attachment.file.open() as f:
            data = f.read()
        self.assertEqual(data, b"Test data 2")

    def test_list_notes(self):
        note = Note.objects.create(personyear=self.person_year, text="Test tekst")
        attachment = NoteAttachment.objects.create(
            note=note,
            file=SimpleUploadedFile(name="testfile", content=b"Test data"),
            content_type="text/plain",
        )
        view = self.view_class()
        request = self.request_factory.get(
            "/persons/{self.person1.pk}/notes/?year=2020", pk=self.person1.pk
        )
        request.user = self.admin_user
        view.setup(request, pk=self.person1.pk)
        with self._time_context():
            response = view.get(request, pk=self.person1.pk)
        self.assertEqual(response.status_code, 200)
        notes = view.get_context_data()["notes"]
        self.assertEqual(notes[0], note)
        self.assertEqual(notes[0].attachments.first(), attachment)

        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 2)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailNotesView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        self.assertEqual(pageview.itemviews.count(), 1)
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, note)

    def test_create_invalid(self):
        view = self.view_class()
        request = self.request_factory.post(
            reverse("suila:person_detail_notes", kwargs={"pk": self.person1.pk}),
            {
                "text": "Test tekst",
            },
            format="multipart",
        )
        request.user = self.admin_user
        view.setup(request, pk=self.person1.pk)
        with self._time_context():
            response = view.post(request, pk=self.person1.pk)
        self.assertEqual(view.get_context_data()["form"].errors, {})
        self.assertEqual(view.get_context_data()["formset"].errors, [])
        self.assertEqual(len(view.get_context_data()["formset"].non_form_errors()), 1)
        qs = Note.objects.filter(personyear=self.person_year)
        self.assertEqual(qs.count(), 0)
        self.assertEqual(response.status_code, 200)

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/notes/?year=2020",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailNotesView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        self.assertEqual(pageview.itemviews.count(), 0)


class TestNoteAttachmentView(TimeContextMixin, PersonEnv):

    view_class = PersonDetailNotesAttachmentView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.note = Note.objects.create(text="Test tekst", personyear=cls.person_year)
        cls.attachment = NoteAttachment.objects.create(
            note=cls.note,
            file=SimpleUploadedFile(
                name="testfile",
                content=b"Test data",
                content_type="text/plain",
            ),
        )

    def test_get(self):
        request = self.request_factory.get(
            reverse("suila:note_attachment", kwargs={"pk": self.attachment.pk})
        )
        request.user = self.admin_user
        view = self.view_class()
        view.setup(request, pk=self.attachment.pk)
        with self._time_context():
            response = view.get(request, pk=self.person1.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Test data")

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"note_attachments/{self.attachment.pk}/",
            pk=self.attachment.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailNotesAttachmentView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.attachment.pk})
        self.assertEqual(pageview.params, {})
        self.assertEqual(pageview.itemviews.count(), 1)
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.attachment)


class TestPermissionsRequiredMixin(TestViewMixin, PersonEnv):
    class SuperView(View):
        def get_object(self, queryset=None):
            return Person.objects.get(cpr="0101013333")

    class ImplView(PermissionsRequiredMixin, SuperView):
        required_object_permissions = []

    view_class = ImplView

    def test_get_object(self):
        view = self.view(self.staff_user)
        self.assertEqual(view.get_object(), self.person3)

        view2 = self.view(self.normal_user)
        view2.required_object_permissions = ["view"]
        with self.assertRaises(PermissionDenied):
            view2.get_object()

    def test_has_permissions(self):
        view = self.view(self.staff_user)
        self.assertTrue(self.ImplView.has_permissions(None, view.request))
        self.assertTrue(self.ImplView.has_permissions(self.staff_user, None))
        with self.assertRaises(ValueError):
            self.ImplView.has_permissions(None, None)


class TestViewLog(TestViewMixin, TestCase):

    class TestView(ViewLogMixin, TemplateView):
        template_name = "suila/root.html"

        def get(self, request, *args, **kwargs):
            self.log_view()
            return super().get(request, *args, **kwargs)

    view_class = TestView

    def test_view_no_user(self):
        with self.assertRaises(ValueError):
            view, response = self.request_get(user=AnonymousUser())


class TestCalculator(TimeContextMixin, PersonEnv, TestCase):
    view_class = CalculatorView

    def request(self, amount):
        view, response = self.request_post(
            self.admin_user,
            reverse("suila:calculator"),
            {
                "estimated_year_income": amount,
                "method": "StandardWorkBenefitCalculationMethod",
                "benefit_rate_percent": "17.5",
                "personal_allowance": "58000.00",
                "standard_allowance": "10000",
                "max_benefit": "15750.00",
                "scaledown_rate_percent": "6.3",
                "scaledown_ceiling": "250000.00",
            },
        )
        return response

    def test_form_valid(self):
        with self._time_context(year=2020):
            view, response = self.request_post(
                self.normal_user,
                reverse("suila:calculator"),
                {
                    "estimated_year_income": "300000",
                    "method": "StandardWorkBenefitCalculationMethod",
                },
            )
            context_data = response.context_data
            self.assertEqual(context_data["yearly_benefit"], "12600.00")
            self.assertEqual(context_data["monthly_benefit"], "1050.00")

    def test_calculator_zero(self):
        response = self.request(0)
        self.assertIsInstance(response, TemplateResponse)
        self.assertTrue(response.context_data["form"].is_valid())
        self.assertEqual(response.context_data["yearly_benefit"], "0.00")
        self.assertEqual(response.context_data["monthly_benefit"], "0.00")
        self.assertJSONEqual(
            response.context_data["graph_points"],
            [
                [0.0, 0.0],
                [68000.0, 0.0],
                [158000.0, 15750.0],
                [250000.0, 15750.0],
                [500000.0, 0.0],
            ],
        )

    def test_calculator_ramp_up(self):
        response = self.request(100000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["yearly_benefit"], "5600.00")
        self.assertEqual(context["monthly_benefit"], "466.67")

    def test_calculator_ramp_plateau(self):
        response = self.request(250000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["yearly_benefit"], "15750.00")
        self.assertEqual(context["monthly_benefit"], "1312.50")

    def test_calculator_ramp_down(self):
        response = self.request(350000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["yearly_benefit"], "9450.00")
        self.assertEqual(context["monthly_benefit"], "787.50")

    def test_calculator_ramp_over(self):
        response = self.request(500000)
        self.assertIsInstance(response, TemplateResponse)
        context = response.context_data
        self.assertTrue(context["form"].is_valid(), context["form"].errors)
        self.assertEqual(context["yearly_benefit"], "0.00")
        self.assertEqual(context["monthly_benefit"], "0.00")

    def test_get_engines(self):
        self.assertEqual(
            self.view().engines,
            [
                {
                    "name": "StandardWorkBenefitCalculationMethod for "
                    + (", ".join(map(str, range(2020, date.today().year + 1)))),
                    "class": "StandardWorkBenefitCalculationMethod",
                    "fields": {
                        "benefit_rate_percent": {
                            "value": Decimal("17.500"),
                            "label": "Benefit rate percent",
                        },
                        "personal_allowance": {
                            "value": Decimal("58000.00"),
                            "label": "Personal allowance",
                        },
                        "standard_allowance": {
                            "value": Decimal("10000.00"),
                            "label": "Standard allowance",
                        },
                        "max_benefit": {
                            "value": Decimal("15750.00"),
                            "label": "Max benefit",
                        },
                        "scaledown_rate_percent": {
                            "value": Decimal("6.300"),
                            "label": "Scaledown rate percent",
                        },
                        "scaledown_ceiling": {
                            "value": Decimal("250000.00"),
                            "label": "Scaledown ceiling",
                        },
                    },
                }
            ],
        )

    def test_view_log(self):
        self.request_get(self.admin_user, "")
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "CalculatorView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {})
        self.assertEqual(pageview.params, {})
        self.assertEqual(pageview.itemviews.count(), 0)


class TestEboksView(TestViewMixin, PersonEnv, TestCase):

    view_class = PersonDetailEboksPreView

    def test_get_context_data(self):
        view, response = self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/eboks/?year={self.person_year.year.year}",
            pk=self.person1.pk,
        )
        context_data = view.get_context_data()
        self.assertQuerySetEqual(
            context_data["months"],
            self.person_year.personmonth_set.all().order_by("month"),
        )
        self.assertQuerySetEqual(
            context_data["available_person_years"],
            PersonYear.objects.filter(person=self.person_year.person).order_by(
                "-year__year"
            ),
        )

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/eboks/?year={self.person_year.year.year}",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailEboksPreView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {"year": "2020"})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, self.person_year)


class EboksTest(TestCase):

    client_cert_file = NamedTemporaryFile(suffix=".crt")
    client_key_file = NamedTemporaryFile(suffix=".key")

    @classmethod
    def test_settings(cls, **kwargs):
        return {
            **settings.EBOKS,
            "client_cert": cls.client_cert_file.name,
            "client_key": cls.client_key_file.name,
            **kwargs,
        }


@override_settings(EBOKS=EboksTest.test_settings())
class TestEboksSendView(TestViewMixin, PersonEnv, EboksTest):

    view_class = PersonDetailEboksSendView

    @staticmethod
    def mock_request(recipient_status, post_processing_status, fails=0, status=200):
        mock = MagicMock()

        def side_effect(method, url, params, data, **kwargs):
            if mock.fails > 0:
                mock.fails -= 1
                raise ConnectionError
            m = re.search(
                r"/int/rest/srv.svc/3/dispatchsystem/3994/dispatches/([^/]+)", url
            )
            if m is None:
                raise Exception("No match")
            message_id = m.group(1)

            response = Response()
            response.status_code = status
            if status == 200:
                response._content = json.dumps(
                    {
                        "message_id": message_id,
                        "recipients": [
                            {
                                "status": recipient_status,
                                "post_processing_status": post_processing_status,
                            }
                        ],
                    }
                ).encode("utf-8")
            return response

        mock.fails = fails
        mock.side_effect = side_effect
        return mock

    def test_get_context_data(self):
        view, response = self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/eboks/send/",
            pk=self.person1.pk,
        )
        context_data = view.get_context_data()
        self.assertEqual(
            context_data["person"],
            self.person1,
        )
        self.assertEqual(
            context_data["person_month"],
            PersonMonth.objects.filter(
                person_year__person=self.person1,
            )
            .order_by("-person_year__year_id", "-month")
            .first(),
        )

    def test_view_log(self):
        self.request_get(
            self.admin_user,
            f"/persons/{self.person1.pk}/send/",
            pk=self.person1.pk,
        )
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "PersonDetailEboksSendView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(pageview.kwargs, {"pk": self.person1.pk})
        self.assertEqual(pageview.params, {})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(
            itemviews[0].item,
            PersonMonth.objects.filter(
                person_year__person=self.person1,
            )
            .order_by("-person_year__year_id", "-month")
            .first(),
        )

    @patch.object(requests.sessions.Session, "request")
    def test_post(self, mock_request: MagicMock):
        mock_request.side_effect = self.mock_request("", "")
        view, response = self.request_post(
            self.admin_user,
            f"/persons/{self.person1.pk}/eboks/send/",
            {"confirmed": "True"},
            pk=self.person1.pk,
        )
        self.assertEqual(response.status_code, 302)
        self.person1.refresh_from_db()
        self.assertIsNotNone(self.person1.welcome_letter)
        message = self.person1.welcome_letter
        contents = message.xml
        if type(contents) is not bytes:
            contents = contents.tobytes()
        mock_request.assert_called_with(
            "PUT",
            f"https://eboxtest.nanoq.gl/int/rest/srv.svc/3/"
            f"dispatchsystem/3994/dispatches/{message.message_id}",
            None,
            contents,
            timeout=60,
        )
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.recipient_status, "")
        self.assertIsNotNone(message.pk)

    @patch.object(requests.sessions.Session, "request")
    def test_post_not_confirmed(self, mock_request):
        mock_request.side_effect = self.mock_request("", "")
        view, response = self.request_post(
            self.admin_user,
            f"/persons/{self.person1.pk}/eboks/send/",
            {"confirmed": "False"},
            pk=self.person1.pk,
        )
        self.assertEqual(response.status_code, 302)
        self.person1.refresh_from_db()
        self.assertIsNone(self.person1.welcome_letter)
        mock_request.assert_not_called()


class TestGeneratedEboksMessageView(TestViewMixin, PersonEnv, TestCase):

    view_class = GeneratedEboksMessageView

    def get(self, user, typ="opgørelse"):
        return self.request_get(
            user,
            f"/persons/{self.person1.pk}/msg/{self.person_year.year.year}/1/opgørelse/",
            pk=self.person1.pk,
            year=self.person_year.year.year,
            month=1,
            type=typ,
        )

    def test_borger_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.get(self.normal_user)

    def test_admin_see_data(self):
        self.get(self.admin_user)

    def test_staff_see_data(self):
        self.get(self.staff_user)

    def test_other_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.get(self.other_user)

    def test_anonymous_see_none(self):
        view, response = self.get(self.no_user)
        self.assertEqual(response.status_code, 302)

    def test_header(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            f"/persons/{self.person1.pk}/msg/{self.person_year.year.year}/1/opgørelse/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_get_context_data(self):
        view, response = self.get(self.admin_user)
        context_data = view.get_context_data()
        personmonth = self.person_year.personmonth_set.get(month=1)
        message = context_data["message"]
        self.assertIsNotNone(message)
        self.assertTrue(isinstance(message, SuilaEboksMessage))
        self.maxDiff = None
        self.assertEqual(
            message.context,
            {
                "person": self.person1,
                "year": personmonth.year,
                "month": personmonth.month,
                "personyear": personmonth.person_year,
                "personmonth": personmonth,
                "sum_income": Decimal("0.00"),
                "income": {
                    # Passer med indkomster der sættes op i PersonEnv.setUpTestData
                    "catchsale_income": [
                        Decimal("0.00"),
                        Decimal("2310.00"),
                        Decimal("0.00"),
                        Decimal("0.00"),
                    ],
                    "salary_income": [
                        Decimal("0.00"),
                        Decimal("2310.00"),
                        Decimal("0.00"),
                        Decimal("0.00"),
                    ],
                    "btax_paid": [
                        Decimal("0.00"),
                        Decimal("770.00"),
                        Decimal("0.00"),
                        Decimal("0.00"),
                    ],
                    "capital_income": [
                        Decimal("0.00"),
                        Decimal("0.00"),
                        Decimal("0.00"),
                        Decimal("0.00"),
                    ],
                },
            },
        )

    def test_view_log(self):
        self.get(self.admin_user)
        personmonth = self.person_year.personmonth_set.get(month=1)
        logs = PageView.objects.all()
        self.assertEqual(logs.count(), 1)
        pageview = logs[0]
        self.assertEqual(pageview.class_name, "GeneratedEboksMessageView")
        self.assertEqual(pageview.user, self.admin_user)
        self.assertEqual(
            pageview.kwargs,
            {"pk": self.person1.pk, "month": 1, "type": "opgørelse", "year": 2020},
        )
        self.assertEqual(pageview.params, {})
        itemviews = list(pageview.itemviews.all())
        self.assertEqual(len(itemviews), 1)
        self.assertEqual(itemviews[0].item, personmonth)

    def test_wrong_type(self):
        with self.assertRaises(Http404):
            self.get(
                self.admin_user,
                "foobar",
            )


class TestEboksMessageView(TestViewMixin, PersonEnv, TestCase):
    view_class = EboksMessageView

    def get(self, user):
        return self.request_get(
            user,
            f"/persons/{self.person1.pk}/msg/",
            pk=self.person1.pk,
        )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person1.welcome_letter = SuilaEboksMessage.objects.create(
            person_month=cls.person1.personyear_set.order_by("-year")
            .first()
            .personmonth_set.order_by("-month")
            .first(),
            type="opgørelse",
        )
        cls.person1.welcome_letter.update_fields(True)
        cls.person1.welcome_letter_sent_at = timezone.now()
        cls.person1.save()

    def test_get_context_data(self):
        view, response = self.get(self.admin_user)
        context_data = view.get_context_data()
        message = context_data["message"]
        self.assertIsNotNone(message)
        self.assertTrue(isinstance(message, SuilaEboksMessage))
        self.maxDiff = None
        self.assertEqual(message, self.person1.welcome_letter)

    def test_borger_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.get(self.normal_user)

    def test_admin_see_data(self):
        self.get(self.admin_user)

    def test_staff_see_data(self):
        self.get(self.staff_user)

    def test_other_see_none(self):
        with self.assertRaises(PermissionDenied):
            self.get(self.other_user)

    def test_anonymous_see_none(self):
        view, response = self.get(self.no_user)
        self.assertEqual(response.status_code, 302)

    def test_header(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(f"/persons/{self.person1.pk}/msg/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")


class TestPersonYearPauseUpdateView(TestViewMixin, PersonEnv):
    view_class = PersonYearPauseUpdateView

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.person_year = PersonYear.objects.all()[0]
        cls.url = reverse("suila:pause_person_year", kwargs={"pk": cls.person_year.pk})
        cls.data = {
            "person_year": cls.person_year.pk,
            "paused": True,
        }

    def test_pause_person_year_as_admin(self):
        self.assertFalse(self.person_year.paused)

        self.client.force_login(self.admin_user)
        self.client.post(self.url, data=self.data)

        self.person_year.refresh_from_db()
        self.assertTrue(self.person_year.paused)

    def test_pause_person_year_as_staff(self):
        self.assertFalse(self.person_year.paused)

        self.client.force_login(self.staff_user)
        self.client.post(self.url, data=self.data)

        self.person_year.refresh_from_db()
        self.assertTrue(self.person_year.paused)

    def test_pause_person_year_as_normal_user(self):
        self.assertFalse(self.person_year.paused)

        self.client.force_login(self.normal_user)
        response = self.client.post(self.url, data=self.data)

        self.assertEqual(response.status_code, 403)

    def test_unpause_person_year(self):
        self.person_year.paused = True
        self.person_year.save()

        self.assertTrue(self.person_year.paused)

        self.client.force_login(self.admin_user)
        self.data["paused"] = False
        self.client.post(self.url, data=self.data)

        self.person_year.refresh_from_db()
        self.assertFalse(self.person_year.paused)
