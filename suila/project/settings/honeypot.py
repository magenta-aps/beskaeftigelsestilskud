from django.template.response import TemplateResponse

HONEYPOT_FIELD_NAME = "asmd"


def HONEYPOT_RESPONDER(request, context):
    return TemplateResponse(
        request=request,
        status=403,
        template="403.html",
    )
