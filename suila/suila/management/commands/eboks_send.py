# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.template.loader import get_template
from pypdf import PdfWriter
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from suila.integrations.eboks.client import EboksClient
from suila.management.commands.common import SuilaBaseCommand
from suila.models import EboksMessage, Person, PersonMonth, PersonYear


class Command(SuilaBaseCommand):
    filename = __file__

    def add_arguments(self, parser):
        parser.add_argument("type", type=str)
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)
        parser.add_argument("--cpr", type=str)
        super().add_arguments(parser)

    type_map = {
        "opgørelse": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Årsopgørelse",
            "template_folder": "suila/eboks/opgørelse",
        },
        "afventer": {
            "content_type": settings.EBOKS["content_type_id"],  # type: ignore
            "title": "Årsopgørelse",
            "template_folder": "suila/eboks/afventer",
        },
    }
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

    def _handle(self, *args, **kwargs):
        client = EboksClient.from_settings()
        typ = kwargs["type"]
        year = kwargs["year"]
        month = kwargs["month"]
        attrs = self.type_map[typ]
        qs = Person.objects.all()
        if kwargs.get("cpr"):
            qs = qs.filter(cpr=kwargs["cpr"])

        title = attrs["title"]
        content_type = attrs["content_type"]

        templates = {
            "kl": get_template(os.path.join(attrs["template_folder"], "kl.html")),
            "da": get_template(os.path.join(attrs["template_folder"], "da.html")),
        }
        for person in qs:
            try:
                personyear: PersonYear = person.personyear_set.get(year_id=year)
                personmonth: PersonMonth = personyear.personmonth_set.get(month=month)
                year_range = range(year, year - 3, -1)
                year_map = [[personmonth]] + [
                    PersonMonth.objects.filter(
                        person_year__person=person, person_year__year_id=y
                    )
                    for y in year_range
                ]
                quant = Decimal("0.01")
                context = {
                    "person": person,
                    "year": year,
                    "month": month,
                    "personyear": personyear,
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
                writer = PdfWriter()
                data = BytesIO()
                for language, template in templates.items():
                    context["month_name"] = self.month_names[language][month - 1]
                    html = template.render(context)
                    font_config = FontConfiguration()
                    pdf_data = HTML(string=html).write_pdf(font_config=font_config)
                    writer.append(BytesIO(pdf_data))
                    writer.write_stream(data)
                data.seek(0)
                EboksMessage.dispatch(
                    person.cpr, title, content_type, data.read(), client
                )
            except PersonYear.DoesNotExist:
                pass
            except PersonMonth.DoesNotExist:
                pass
