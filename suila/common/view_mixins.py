# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from typing import List

from common.models import ItemView, PageView, User
from django.db.models import Model, QuerySet
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.edit import BaseFormView


class ViewLogMixin:
    def log_view(
        self,
        items: Model | List[Model] | QuerySet[Model] | None = None,
    ) -> PageView | None:
        request = self.request  # type: ignore[attr-defined]
        user = request.user
        if not isinstance(user, User):
            raise ValueError
        pageview = PageView.objects.create(
            user=request.user,  # type: ignore[misc]
            url=request.build_absolute_uri(),
            class_name=self.__class__.__name__,
            kwargs=self.kwargs,  # type: ignore[attr-defined]
            params=request.GET.dict(),
        )
        if items is not None:
            if isinstance(items, Model):
                items = [items]
            ItemView.objects.bulk_create(
                [ItemView(pageview=pageview, item=item) for item in items]
            )
        return pageview


class BaseGetFormView(BaseFormView):

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == "GET":
            kwargs["data"] = self.request.GET
        return kwargs

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class GetFormView(TemplateResponseMixin, BaseGetFormView):
    pass
