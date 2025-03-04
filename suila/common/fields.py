from django.forms import RegexField


class CPRField(RegexField):
    def __init__(self, **kwargs):
        super().__init__(r"^\d{6}-{0,1}\d{4}$", **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        # Remove dash in CPR, if given
        if isinstance(value, str):
            value = value.strip()
            if "-" in value:
                value = value.replace("-", "")
        return value
