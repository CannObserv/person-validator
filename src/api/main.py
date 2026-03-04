"""FastAPI application factory for the Person Validator API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health_router, v1_router
from src.core.logging import configure_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title="Person Validator API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(v1_router)

    return app
