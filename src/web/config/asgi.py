"""ASGI config for Person Validator."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.web.config.settings")

application = get_asgi_application()
