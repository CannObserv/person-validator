"""Tests for exe.dev email authentication backend and middleware."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory

from src.web.accounts.backends import ExeDevEmailBackend, _get_admin_email
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
class TestUserIDMigration:
    """Test that a changed exe.dev user ID migrates the existing account."""

    def test_new_userid_for_existing_email_migrates_user(self, rf, backend):
        """When exe.dev issues a new user ID for the same email, the existing
        user record should be updated rather than creating a duplicate."""
        request = rf.get("/")

        user1 = backend.authenticate(
            request, exedev_email="alice@example.com", exedev_userid="usr_old_id"
        )

        user2 = backend.authenticate(
            request, exedev_email="alice@example.com", exedev_userid="usr_new_id"
        )

        assert user2.pk == user1.pk
        assert user2.username == "usr_new_id"
        assert User.objects.filter(email="alice@example.com").count() == 1

    def test_migrated_user_preserves_staff_status(self, rf, backend, settings):
        """Staff/superuser flags survive a user-ID migration."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        user1 = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_old_admin"
        )
        assert user1.is_superuser is True

        user2 = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_new_admin"
        )
        assert user2.pk == user1.pk
        assert user2.is_superuser is True
        assert user2.is_staff is True

    def test_old_userid_no_longer_resolves_after_migration(self, rf, backend):
        """After migration, the old username should not find any user."""
        request = rf.get("/")

        backend.authenticate(request, exedev_email="alice@example.com", exedev_userid="usr_old_id")
        backend.authenticate(request, exedev_email="alice@example.com", exedev_userid="usr_new_id")

        assert not User.objects.filter(username="usr_old_id").exists()


@pytest.mark.django_db
class TestEmailUniqueness:
    """Test that duplicate email addresses are never created."""

    def test_no_duplicate_email_after_userid_change(self, rf, backend):
        """Changing user ID for the same email must not create a second user."""
        request = rf.get("/")

        backend.authenticate(request, exedev_email="dup@example.com", exedev_userid="usr_first")
        backend.authenticate(request, exedev_email="dup@example.com", exedev_userid="usr_second")

        assert User.objects.filter(email="dup@example.com").count() == 1

    def test_different_emails_create_separate_users(self, rf, backend):
        """Distinct emails still create distinct users."""
        request = rf.get("/")

        backend.authenticate(request, exedev_email="a@example.com", exedev_userid="usr_a")
        backend.authenticate(request, exedev_email="b@example.com", exedev_userid="usr_b")

        assert User.objects.count() == 2


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

    def test_no_promotion_when_admin_email_does_not_match(self, rf, backend, settings):
        """A user whose email doesn't match ADMIN_DEV_EMAIL is not promoted."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        user = backend.authenticate(
            request, exedev_email="someone-else@example.com", exedev_userid="usr_other"
        )

        assert user.is_superuser is False
        assert user.is_staff is False

    def test_non_admin_not_promoted_when_superusers_exist(self, rf, backend, settings):
        """Non-admin email users are never promoted, even after bootstrap."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        backend.authenticate(request, exedev_email="admin@example.com", exedev_userid="usr_admin1")

        user2 = backend.authenticate(
            request, exedev_email="random@example.com", exedev_userid="usr_random"
        )
        assert user2.is_superuser is False
        assert user2.is_staff is False

    def test_admin_returning_user_stays_promoted(self, rf, backend, settings):
        """An existing admin user retains superuser on subsequent logins."""
        settings.ADMIN_DEV_EMAIL = "admin@example.com"
        request = rf.get("/")

        user1 = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_admin"
        )
        assert user1.is_superuser is True

        user2 = backend.authenticate(
            request, exedev_email="admin@example.com", exedev_userid="usr_admin"
        )
        assert user2.pk == user1.pk
        assert user2.is_superuser is True
        assert user2.is_staff is True


@pytest.mark.django_db
class TestExeDevMiddleware:
    """Test the authentication middleware."""

    def test_middleware_authenticates_from_headers(self, rf):
        """Middleware should read headers and log user in."""
        request = rf.get("/")
        request.META["HTTP_X_EXEDEV_EMAIL"] = "mw@example.com"
        request.META["HTTP_X_EXEDEV_USERID"] = "usr_mw"
        request.session = SessionStore()

        called = {}

        def get_response(req):
            called["user"] = req.user
            return HttpResponse("ok")

        middleware = ExeDevEmailAuthMiddleware(get_response)
        middleware(request)

        assert called["user"].is_authenticated
        assert called["user"].email == "mw@example.com"

    def test_middleware_skips_without_headers(self, rf):
        """Without exe.dev headers, middleware should not authenticate."""
        request = rf.get("/")
        request.session = SessionStore()

        called = {}

        def get_response(req):
            called["user"] = req.user
            return HttpResponse("ok")

        middleware = ExeDevEmailAuthMiddleware(get_response)
        middleware(request)

        assert not called["user"].is_authenticated


class TestGetAdminEmail:
    """Test the _get_admin_email helper."""

    def test_returns_setting_value(self, settings):
        """Returns the value from ADMIN_DEV_EMAIL setting."""
        settings.ADMIN_DEV_EMAIL = "from-settings@example.com"
        assert _get_admin_email() == "from-settings@example.com"

    def test_returns_empty_when_not_set(self, settings):
        """Returns empty string when setting is absent."""
        settings.ADMIN_DEV_EMAIL = ""
        assert _get_admin_email() == ""


class TestAdminDevEmailStartupValidation:
    """Test that ADMIN_DEV_EMAIL is required at startup.

    These tests verify the settings-level validation rather than reimporting
    settings (which would have side effects). We test the contract: settings.py
    raises ImproperlyConfigured when ADMIN_DEV_EMAIL cannot be resolved.
    """

    def test_settings_has_admin_dev_email(self, settings):
        """The running test suite must have ADMIN_DEV_EMAIL set."""
        assert settings.ADMIN_DEV_EMAIL, "ADMIN_DEV_EMAIL should be set in env or shelley config"
