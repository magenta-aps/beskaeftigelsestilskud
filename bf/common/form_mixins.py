from django.forms import forms


class BootstrapForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(BootstrapForm, self).__init__(*args, **kwargs)
        self.kwargs = kwargs
        for name, field in self.fields.items():
            self.update_field(name, field)
            self.set_field_classes(name, field)

    def full_clean(self):
        result = super(BootstrapForm, self).full_clean()
        self.set_all_field_classes()
        return result

    def set_all_field_classes(self):
        for name, field in self.fields.items():
            self.set_field_classes(name, field, True)

    def set_field_classes(self, name, field, check_for_errors=False):
        classes = self.split_class(field.widget.attrs.get("class"))
        classes.append("mr-2")
        # if isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
        #     pass
        # else:
        classes.append("form-control")
        # if isinstance(field.widget, forms.Select):
        #     classes.append("form-select")

        # if check_for_errors:
        #     if self.has_error(name) is True:
        #         classes.append("is-invalid")
        field.widget.attrs["class"] = " ".join(set(classes))

    @staticmethod
    def split_class(class_string):
        return class_string.split(" ") if class_string else []

    def update_field(self, name, field):
        pass
        # if isinstance(field.widget, forms.FileInput):
        #     field.widget.template_name = "told_common/widgets/file.html"
        #     if "class" not in field.widget.attrs:
        #         field.widget.attrs["class"] = ""
        #     field.widget.attrs["class"] += " custom-file-input"
