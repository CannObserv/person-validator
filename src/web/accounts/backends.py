"""exe.dev email-based authentication backend."""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def _get_admin_email() -> str:
    """Resolve the admin bootstrap email using priority chain.

    Priority:
    1. ADMIN_DEV_EMAIL from Django settings (sourced from env file)
    2. Email from ~/.config/shelley/AGENTS.md
    """
    # Priority 1: settings
    admin_email = getattr(settings, "ADMIN_DEV_EMAIL", "")
    if admin_email:
        return admin_email

    # Priority 2: shelley config
    try:
        from pathlib import Path

        agents_path = Path.home() / ".config" / "shelley" / "AGENTS.md"
        if agents_path.exists():
            content = agents_path.read_text()
            # Look for email pattern in the file
            import re

            match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", content)
            if match:
                return match.group(0)
    except Exception:
        logger.debug("Could not read shelley AGENTS.md for admin email", exc_info=True)

    return ""


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

        # Create new user
        user = User.objects.create_user(
            username=exedev_userid,
            email=exedev_email,
        )

        # Superuser bootstrap: only when no superusers exist yet
        if not User.objects.filter(is_superuser=True).exists():
            admin_email = _get_admin_email()
            # Priority 0: the current authenticated email from X-ExeDev-Email
            # (the issue says "X-ExeDev-Email header (current authenticated user)" is priority 1)
            # If no ADMIN_DEV_EMAIL is set, any first user gets promoted
            # If ADMIN_DEV_EMAIL is set, only matching email gets promoted
            if not admin_email or exedev_email == admin_email:
                user.is_superuser = True
                user.is_staff = True
                user.save(update_fields=["is_superuser", "is_staff"])
                logger.info("Bootstrapped superuser: %s (%s)", exedev_email, exedev_userid)

        return user

    def get_user(self, user_id):
        """Retrieve a user by primary key."""
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
