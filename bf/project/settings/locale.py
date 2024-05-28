import django.conf.locale

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "da-dk"
LANGUAGES = [
    ("da", "Dansk"),
    ("kl", "Kalaallisut"),
]
EXTRA_LANG_INFO = {
    "kl": {
        "code": "kl",
        "name": "Kalaallisut",
        "name_local": "Kalaallisut",
        "bidi": False,
    },
}
LANG_INFO = dict(django.conf.locale.LANG_INFO, **EXTRA_LANG_INFO)
django.conf.locale.LANG_INFO = LANG_INFO


TIME_ZONE = "America/Godthab"
USE_I18N = True
USE_L10N = True
USE_TZ = True
THOUSAND_SEPARATOR = "."
DECIMAL_SEPARATOR = ","
