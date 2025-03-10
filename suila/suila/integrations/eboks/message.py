from decimal import Decimal
from functools import cached_property
from io import BytesIO

from django.conf import settings
from django.template.loader import get_template
from django.utils import timezone
from pypdf import PdfWriter
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from suila.integrations.eboks.client import EboksClient
from suila.models import EboksMessage, PersonMonth


class SuilaEboksMessage:

    type_map = {
        "opgørelse": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Årsopgørelse",
            "template_folder": "suila/eboks/opgørelse",
            "templates": {
                "kl": get_template("suila/eboks/opgørelse/kl.html"),
                "da": get_template("suila/eboks/opgørelse/da.html"),
            },
        },
        "afventer": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Årsopgørelse",
            "template_folder": "suila/eboks/afventer",
            "templates": {
                "kl": get_template("suila/eboks/afventer/kl.html"),
                "da": get_template("suila/eboks/afventer/da.html"),
            },
        },
    }

    welcome_letter = "opgørelse"
    month_names = {
        "da": [
            "januar",
            "februar",
            "marts",
            "april",
            "maj",
            "juni",
            "juli",
            "august",
            "september",
            "oktober",
            "november",
            "december",
        ],
        "kl": [
            "januaari",
            "februaari",
            "marsi",
            "apriili",
            "maaji",
            "juuni",
            "juuli",
            "aggusti",
            "septembari",
            "oktobari",
            "novembari",
            "decembari",
        ],
    }

    def __init__(self, personmonth: PersonMonth, typ: str):
        self.personmonth = personmonth
        self.typ = typ
        self.attrs = self.type_map[typ]
        self.month = personmonth.month
        self.year = personmonth.year
        self.person = personmonth.person
        quant = Decimal("0.01")
        year_range = range(self.year, self.year - 3, -1)
        year_map = [[personmonth]] + [
            PersonMonth.objects.filter(
                person_year__person=self.person, person_year__year_id=y
            )
            for y in year_range
        ]
        self.context = {
            "person": self.person,
            "year": personmonth.year,
            "month": personmonth.month,
            "personyear": personmonth.person_year,
            "personmonth": personmonth,
            "income": {
                "catchsale_income": [
                    Decimal(
                        sum(
                            [
                                report.catchsale_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "salary_income": [
                    Decimal(
                        sum(
                            [
                                report.salary_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "btax_paid": [
                    Decimal(
                        sum(
                            [
                                payment.amount_paid
                                for pm in months
                                for payment in pm.btaxpayment_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
                "capital_income": [
                    Decimal(
                        sum(
                            [
                                report.salary_income
                                for pm in months
                                for report in pm.monthlyincomereport_set.all()
                            ]
                        )
                    ).quantize(quant)
                    for months in year_map
                ],
            },
        }

    @property
    def title(self):
        return self.attrs["title"]

    @property
    def content_type(self):
        return self.attrs["content_type"]

    def html(self, language: str):
        template = self.attrs["templates"][language]
        context = {
            **self.context,
            "month_name": self.month_names[language][self.month - 1],
        }
        return template.render(context)

    @cached_property
    def html_kl(self):
        return self.html("kl")

    @cached_property
    def html_da(self):
        return self.html("da")

    @cached_property
    def pdf(self) -> bytes:
        font_config = FontConfiguration()
        writer = PdfWriter()
        data = BytesIO()
        for html in (self.html_kl, self.html_da):
            pdf_data = HTML(string=html).write_pdf(font_config=font_config)
            writer.append(BytesIO(pdf_data))
            writer.write_stream(data)
        data.seek(0)
        return data.read()

    def send(self, client: EboksClient):
        return EboksMessage.dispatch(
            self.person.cpr, self.title, self.content_type, self.pdf, client
        )

    def update_welcome_letter(self, message: EboksMessage):
        if self.typ == self.welcome_letter:
            self.person.welcome_letter = message
            self.person.welcome_letter_sent_at = timezone.now()
            self.person.save(update_fields=("welcome_letter", "welcome_letter_sent_at"))
