"""exe.dev email-based authentication backend."""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def _get_admin_email() -> str:
    """Return the configured admin bootstrap email.

    Reads from ``settings.ADMIN_DEV_EMAIL``, which is resolved at startup
    from the env file or ~/.config/shelley/AGENTS.md (see settings.py).
    Settings validation guarantees this is non-empty at boot time.
    """
    return getattr(settings, "ADMIN_DEV_EMAIL", "")


class ExeDevEmailBackend:
    """Authenticate users via exe.dev proxy headers.

    Reads X-ExeDev-Email and X-ExeDev-UserID headers. Auto-creates users
    on first visit. Bootstraps superuser when no superusers exist.
    """

    def authenticate(self, request=None, exedev_email=None, exedev_userid=None, **kwargs):
        """Authenticate a user from exe.dev proxy headers.

        Args:
            request: The HTTP request.
            exedev_email: Email from X-ExeDev-Email header.
            exedev_userid: User ID from X-ExeDev-UserID header.

        Returns:
            User instance or None.
        """
        if not exedev_email or not exedev_userid:
            return None

        User = get_user_model()

        # Look up by username (stable exe.dev user ID)
        try:
            user = User.objects.get(username=exedev_userid)
            # Update email if it changed
            if user.email != exedev_email:
                user.email = exedev_email
                user.save(update_fields=["email"])
            return user
        except User.DoesNotExist:
            pass

        # Check for an existing user with this email whose user-ID has
        # changed (e.g. exe.dev account migration).  Migrate the record
        # to the new username rather than creating a duplicate.
        try:
            user = User.objects.get(email=exedev_email)
            old_username = user.username
            user.username = exedev_userid
            user.save(update_fields=["username"])
            logger.info(
                "Migrated user %s from username %s to %s",
                exedev_email,
                old_username,
                exedev_userid,
            )
            return user
        except User.DoesNotExist:
            pass

        # Create new user — no existing record for this userid or email.
        user = User.objects.create_user(
            username=exedev_userid,
            email=exedev_email,
        )

        # Admin promotion: grant staff + superuser to the configured admin
        # email on first account creation.
        if exedev_email == _get_admin_email():
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
            logger.info("Promoted admin user: %s (%s)", exedev_email, exedev_userid)

        return user

    def get_user(self, user_id):
        """Retrieve a user by primary key."""
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
