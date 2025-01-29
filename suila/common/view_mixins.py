from typing import List

from common.models import ItemView, PageView, User
from django.db.models import Model, QuerySet


class ViewLogMixin:
    def log_view(
        self,
        items: Model | List[Model] | QuerySet[Model] | None = None,
    ) -> PageView | None:
        request = self.request
        user = request.user
        if type(user) is not User:
            return None
        pageview = PageView.objects.create(
            user=request.user,  # type: ignore[misc]
            url=request.build_absolute_uri(),
            class_name=self.__class__.__name__,
            kwargs=self.kwargs,
            params=request.GET.dict(),
        )
        if items is not None:
            if isinstance(items, Model):
                items = [items]
            ItemView.objects.bulk_create(
                [ItemView(pageview=pageview, item=item) for item in items]
            )
        return pageview
