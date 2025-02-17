# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import itertools
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from common.models import PageView, User
from common.tests.test_mixins import TestViewMixin
from common.view_mixins import ViewLogMixin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.client import RequestFactory
from django.test.testcases import SimpleTestCase
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import ContextMixin, TemplateView, View

from suila.benefit import get_payout_date
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
    Year,
)
from suila.view_mixins import PermissionsRequiredMixin
from suila.views import (
    CalculateBenefitView,
    CPRField,
    IncomeSignal,
    IncomeSignalTable,
    IncomeSignalType,
    IncomeSumsBySignalTypeTable,
    PersonDetailIncomeView,
    PersonDetailNotesAttachmentView,
    PersonDetailNotesView,
    PersonDetailView,
    PersonFilterSet,
    PersonMonthTable,
    PersonSearchView,
    PersonTable,
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
        year = Year.objects.create(year=2020, calculation_method=calc)
        Year.objects.create(year=2021, calculation_method=calc)

        # Add "signal" data to person 1
        cls.person_year, _ = PersonYear.objects.update_or_create(
            person=cls.person1,
            year=year,
            preferred_estimation_engine_a="InYearExtrapolationEngine",
            preferred_estimation_engine_b="InYearExtrapolationEngine",
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
            [person.cpr.zfill(10) for person in Person.objects.all()],
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
        with self._time_context(year=2020):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            # Verify that expected context variables are present
            self.assertIn("next_payout_date", response.context_data)
            self.assertIn("benefit_paid", response.context_data)
            self.assertIn("estimated_year_benefit", response.context_data)
            self.assertIn("estimated_year_result", response.context_data)
            self.assertIn("table", response.context_data)
            # Verify the values of the context variables
            self.assertEqual(
                response.context_data["next_payout_date"], get_payout_date(2020, 12)
            )
            self.assertEqual(response.context_data["benefit_paid"], Decimal("12.0"))
            self.assertIsNone(response.context_data["estimated_year_benefit"])
            self.assertIsNone(response.context_data["estimated_year_result"])
            self.assertIsInstance(response.context_data["table"], PersonMonthTable)
            self.assertFalse(response.context_data["table"].orderable)

    def test_get_context_data_handles_no_matching_person_month(self):
        # Arrange: go to year without `PersonMonth` objects for `normal_user`
        with self._time_context(year=2021):
            view, response = self.request_get(self.normal_user, pk=self.person1.pk)
            self.assertTrue(response.context_data["no_current_month"])

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


class TestCalculateBenefitView(TimeContextMixin, PersonEnv):
    view_class = CalculateBenefitView

    def test_form_valid(self):
        with self._time_context(year=2020):
            view, response = self.request_post(
                self.normal_user,
                reverse("suila:calculate_benefit"),
                {"estimated_year_income": "300000"},
            )
            context_data = response.context_data
            self.assertEqual(context_data["yearly_benefit"], Decimal("12600.00"))
            self.assertEqual(context_data["monthly_benefit"], Decimal("1050.00"))


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
