"""Middleware for exe.dev email-based authentication."""

from django.contrib.auth import authenticate, login
from django.contrib.auth.models import AnonymousUser


class ExeDevEmailAuthMiddleware:
    """Authenticate requests using exe.dev proxy headers.

    Reads X-ExeDev-Email and X-ExeDev-UserID from request headers
    and authenticates the user automatically.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Process the request, authenticating from headers if present."""
        # Only attempt auth if not already authenticated
        if not hasattr(request, "user") or not request.user.is_authenticated:
            email = request.META.get("HTTP_X_EXEDEV_EMAIL")
            userid = request.META.get("HTTP_X_EXEDEV_USERID")

            if email and userid:
                user = authenticate(
                    request,
                    exedev_email=email,
                    exedev_userid=userid,
                )
                if user is not None:
                    login(request, user)
                    request.user = user
                else:
                    request.user = AnonymousUser()
            else:
                if not hasattr(request, "user"):
                    request.user = AnonymousUser()

        return self.get_response(request)
