# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import time
from binascii import unhexlify
from http import HTTPStatus
from unittest.mock import patch

from bs4 import BeautifulSoup
from common.models import User
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.auth.models import Group
from django.shortcuts import resolve_url
from django.test import RequestFactory, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.util import random_hex
from login import views
from login.views import on_session_expired
from two_factor.utils import totp_digits


def totp_str(key):
    return str(totp(key)).zfill(totp_digits())


@override_settings(BYPASS_2FA=False, REQUIRE_2FA=True)
class LoginTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = Group.objects.create(name="Borgerservice")
        cls.user = User.objects.create(username="test")
        cls.user.set_password("test")
        cls.user.save()
        cls.user.groups.add(cls.group)

    @override_settings(PUBLIC=False)
    def test_django_login_form(self):
        self.client.get(reverse("login:login") + "?back=/foobar")
        response = self.client.post(
            reverse("login:login"),
            {
                "auth-username": "test",
                "auth-password": "test",
                "besk_login_view-current_step": "auth",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], settings.LOGIN_REDIRECT_URL)
        response = self.client.get(reverse("login:login") + "?back=/foobar")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/foobar")

    @override_settings(PUBLIC=True)
    def test_saml_postlogin(self):
        session = self.client.session
        session.update(
            {
                "saml": {
                    "ava": {
                        "cpr": ["1234567890"],
                        "cvr": ["12345678"],
                        "firstname": ["Test"],
                        "lastname": ["Testersen"],
                        "email": ["test@example.com"],
                    }
                }
            }
        )
        session.save()
        response = self.client.get(reverse("login:login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    @override_settings(PUBLIC=False, LANGUAGE_CODE="da-dk")
    def test_django_login_form_incorrect(self):
        self.client.get(reverse("login:login"))
        response = self.client.post(
            reverse("login:login"),
            {
                "auth-username": "test",
                "auth-password": "incorrect",
                "besk_login_view-current_step": "auth",
            },
        )
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, "html.parser")
        alert = soup.find(class_="errorlist")
        self.assertIsNotNone(alert)
        self.assertIn("Indtast venligst korrekt brugernavn og adgangskode", str(alert))

    @override_settings(PUBLIC=True)
    def test_saml_logout_redirect(self):
        self.client.login(username="test", password="test")
        session = self.client.session
        session.update(
            {
                BACKEND_SESSION_KEY: "django_mitid_auth.saml.backend.Saml2Backend",
                "saml": {"cpr": "1234567890"},
            }
        )
        session.save()
        response = self.client.get(reverse("login:logout"))
        self.assertEqual(response.headers["Location"], reverse("login:mitid:logout"))

    @override_settings(PUBLIC=False)
    def test_django_logout_redirect(self):
        self.client.login(username="test", password="test")
        response = self.client.get(reverse("login:logout"))
        self.assertEqual(response.headers["Location"], settings.LOGOUT_REDIRECT_URL)

    @override_settings(PUBLIC=False)
    def test_django_login_back(self):
        self.client.cookies["back"] = "/foobar"
        self.client.post(
            reverse("login:login"),
            {
                "auth-username": "test",
                "auth-password": "test",
                "besk_login_view-current_step": "auth",
            },
        )
        response = self.client.get(reverse("login:login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/foobar")

    @override_settings(PUBLIC=True)
    def test_saml_login_back(self):
        session = self.client.session
        session.update(
            {
                "saml": {
                    "ava": {
                        "cpr": ["1234567890"],
                        "cvr": ["12345678"],
                        "firstname": ["Test"],
                        "lastname": ["Testersen"],
                        "email": ["test@example.com"],
                    }
                },
            }
        )
        session.save()
        self.client.cookies["back"] = "/foobar"
        response = self.client.get(reverse("login:login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/foobar")

    @override_settings(PUBLIC=False, LANGUAGE_CODE="da-dk")
    def test_token_step(self):
        device = self.user.totpdevice_set.create(name="default", key=random_hex())
        data = {
            "auth-username": "test",
            "auth-password": "test",
            "besk_login_view-current_step": "auth",
        }
        response = self.client.post(reverse("login:login"), data)
        self.assertContains(response, "Kode:")

        data = {
            "token-otp_token": "123456",
            "besk_login_view-current_step": "token",
        }
        response = self.client.post(reverse("login:login"), data)
        self.assertEqual(
            response.context_data["wizard"]["form"].errors,
            {
                "__all__": [
                    "Invalid token. Please make sure you have entered it correctly."
                ]
            },
        )

        data = {
            "token-otp_token": totp_str(device.bin_key),
            "besk_login_view-current_step": "token",
        }
        device.throttle_reset()

        response = self.client.post(reverse("login:login"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"], resolve_url(settings.LOGIN_REDIRECT_URL)
        )

    @override_settings(BYPASS_2FA=True)
    def test_bypass_token_step(self):
        self.user.totpdevice_set.create(name="default", key=random_hex())

        data = {
            "auth-username": "test",
            "auth-password": "test",
            "besk_login_view-current_step": "auth",
        }
        response = self.client.post(reverse("login:login"), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"], resolve_url(settings.LOGIN_REDIRECT_URL)
        )

    @override_settings(PUBLIC=False, LANGUAGE_CODE="da-dk")
    def test_two_factor_setup(self):
        self.client.login(username="test", password="test")

        response = self.client.post(
            reverse("login:two_factor_setup"),
            data={"two_factor_setup-current_step": "generator"},
        )

        self.assertEqual(
            response.context_data["wizard"]["form"].errors,
            {"token": ["Dette felt er påkrævet."]},
        )

        response = self.client.post(
            reverse("login:two_factor_setup"),
            data={
                "two_factor_setup-current_step": "generator",
                "generator-token": "123456",
            },
        )
        self.assertEqual(
            response.context_data["wizard"]["form"].errors,
            {"token": ["Den indtastet kode er ikke gyldig."]},
        )

        key = response.context_data["keys"].get("generator")
        bin_key = unhexlify(key.encode())
        response = self.client.post(
            reverse("login:two_factor_setup"),
            data={
                "two_factor_setup-current_step": "generator",
                "generator-token": totp(bin_key),
            },
        )

        success_url = reverse("suila:root") + "?two_factor_success=1"

        self.assertEqual(1, self.user.totpdevice_set.count())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], success_url)

    @override_settings(PUBLIC=False)
    def test_2fa_required(self):
        self.client.login(username="test", password="test")
        self.assertEqual(0, self.user.totpdevice_set.count())

        response = self.client.get(reverse("suila:root"))

        self.assertTemplateUsed(response, "two_factor/core/otp_required.html")
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    @override_settings(PUBLIC=True)
    def test_saml_redirect(self):
        session = self.client.session
        session["saml"] = {"cpr": "1234567890"}
        session.save()
        response = self.client.get(reverse("login:login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("login:mitid:login"))

    def test_session_expired_call(self):
        session = self.client.session
        session["_session_init_timestamp_"] = time.time() - 10
        session.save()
        with self.settings(SESSION_EXPIRE_SECONDS=1):
            with patch.object(views, "on_session_expired") as mock_method:
                mock_method.return_value = None
                self.client.get("/")
                mock_method.assert_called()

    def test_on_session_expired(self):
        request_factory = RequestFactory()
        self.assertIsNone(
            on_session_expired(
                request_factory.get(reverse("login:mitid:logout-callback"))
            )
        )
        with self.settings(SESSION_TIMEOUT_REDIRECT=reverse("suila:root")):
            response = on_session_expired(
                request_factory.get(reverse("suila:person_search"))
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("location"), reverse("suila:root"))
        with self.settings(SESSION_TIMEOUT_REDIRECT=None):
            response = on_session_expired(
                request_factory.get(reverse("suila:person_search"))
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response.headers.get("location"),
                reverse("login:login") + "?next=" + reverse("suila:person_search"),
            )
