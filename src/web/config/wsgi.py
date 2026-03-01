"""WSGI config for Person Validator."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.web.config.settings")

application = get_wsgi_application()
