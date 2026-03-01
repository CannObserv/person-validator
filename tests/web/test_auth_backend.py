"""Tests for exe.dev email authentication backend and middleware."""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from src.web.accounts.backends import ExeDevEmailBackend
from src.web.accounts.middleware import ExeDevEmailAuthMiddleware

User = get_user_model()


@pytest.fixture()
def rf():
    """Django request factory."""
    return RequestFactory()


@pytest.fixture()
def backend():
    """Auth backend instance."""
    return ExeDevEmailBackend()


@pytest.mark.django_db
class TestExeDevEmailBackend:
    """Test the custom authentication backend."""

    def test_authenticate_creates_user_on_first_visit(self, rf, backend):
        """A new user should be auto-created from headers."""
        request = rf.get("/")
        request.META["HTTP_X_EXEDEV_EMAIL"] = "alice@example.com"
        request.META["HTTP_X_EXEDEV_USERID"] = "usr_alice123"

        user = backend.authenticate(
            request, exedev_email="alice@example.com", exedev_userid="usr_alice123"
        )

        assert user is not None
        assert user.email == "alice@example.com"
        assert user.username == "usr_alice123"
        assert User.objects.filter(email="alice@example.com").exists()

    def test_authenticate_returns_existing_user(self, rf, backend):
        """Second auth with same headers returns the same user."""
        request = rf.get("/")
        request.META["HTTP_X_EXEDEV_EMAIL"] = "bob@example.com"
        request.META["HTTP_X_EXEDEV_USERID"] = "usr_bob456"

        user1 = backend.authenticate(
            request, exedev_email="bob@example.com", exedev_userid="usr_bob456"
        )
        user2 = backend.authenticate(
            request, exedev_email="bob@example.com", exedev_userid="usr_bob456"
        )

        assert user1.pk == user2.pk
        assert User.objects.filter(email="bob@example.com").count() == 1

    def test_authenticate_returns_none_without_email(self, rf, backend):
        """Missing email header should return None."""
        request = rf.get("/")
        user = backend.authenticate(request)
        assert user is None

    def test_authenticate_returns_none_without_userid(self, rf, backend):
        """Missing userid header should return None."""
        request = rf.get("/")
        user = backend.authenticate(request, exedev_email="alice@example.com")
        assert user is None

    def test_authenticate_updates_email_on_userid_match(self, rf, backend):
        """If userid matches but email changed, update the email."""
        request = rf.get("/")
        backend.authenticate(request, exedev_email="old@example.com", exedev_userid="usr_same")
        user = backend.authenticate(
            request, exedev_email="new@example.com", exedev_userid="usr_same"
        )

        assert user.email == "new@example.com"

    def test_get_user_returns_user(self, rf, backend):
        """get_user should return user by pk."""
        request = rf.get("/")
        user = backend.authenticate(
            request, exedev_email="carol@example.com", exedev_userid="usr_carol"
        )
        assert backend.get_user(user.pk) == user

    def test_get_user_returns_none_for_missing(self, backend):
        """get_user returns None for non-existent pk."""
        assert backend.get_user(999999) is None


@pytest.mark.django_db
class TestSuperuserBootstrap:
    """Test automatic superuser promotion."""

    def test_first_matching_email_becomes_superuser(self, rf, backend, settings):
        """The admin email should be promoted to superuser."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        user = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_admin"
        )

        assert user.is_superuser is True
        assert user.is_staff is True

    def test_non_admin_email_is_not_superuser(self, rf, backend, settings):
        """Regular users should not get superuser."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        user = backend.authenticate(
            request, exedev_email="regular@example.com", exedev_userid="usr_regular"
        )

        assert user.is_superuser is False
        assert user.is_staff is False

    def test_superuser_bootstrap_only_when_no_superusers_exist(self, rf, backend, settings):
        """Once a superuser exists, no more auto-promotion."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        # First admin bootstrapped
        backend.authenticate(request, exedev_email="admin@example.com", exedev_userid="usr_admin1")

        # Second matching email should NOT be promoted
        user2 = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_admin2"
        )
        # Already a superuser exists, so this new user should not be auto-promoted
        # (they'll be a new user since different userid)
        assert user2.is_superuser is False


@pytest.mark.django_db
class TestExeDevMiddleware:
    """Test the authentication middleware."""

    def test_middleware_authenticates_from_headers(self, rf):
        """Middleware should read headers and log user in."""
        request = rf.get("/")
        request.META["HTTP_X_EXEDEV_EMAIL"] = "mw@example.com"
        request.META["HTTP_X_EXEDEV_USERID"] = "usr_mw"

        # Simulate session middleware
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()

        called = {}

        def get_response(req):
            called["user"] = req.user
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = ExeDevEmailAuthMiddleware(get_response)
        middleware(request)

        assert called["user"].is_authenticated
        assert called["user"].email == "mw@example.com"

    def test_middleware_skips_without_headers(self, rf):
        """Without exe.dev headers, middleware should not authenticate."""
        request = rf.get("/")

        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()

        called = {}

        def get_response(req):
            called["user"] = req.user
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = ExeDevEmailAuthMiddleware(get_response)
        middleware(request)

        assert not called["user"].is_authenticated
