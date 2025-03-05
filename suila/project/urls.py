# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

"""
URL configuration for suila project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog
from two_factor.urls import urlpatterns as tf_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path(
        "",
        include(
            "suila.urls",
            namespace="suila",
        ),
    ),
    path(
        "",
        include(
            "login.urls",
            namespace="login",
        ),
    ),
    path(
        "analysis/",
        include(
            "data_analysis.urls",
            namespace="data_analysis",
        ),
    ),
    path(
        "update/",
        include(
            "data_update.urls",
            namespace="data_update",
        ),
    ),
    path("", include(tf_urls)),
] + debug_toolbar_urls()

if settings.MITID_TEST_ENABLED:  # type: ignore[misc]
    urlpatterns.append(
        path("mitid_test/", include("mitid_test.urls", namespace="mitid_test"))
    )
