"""ASGI entrypoint for uvicorn: ``uvicorn src.api.asgi:app``."""

from src.api.main import create_app

app = create_app()
