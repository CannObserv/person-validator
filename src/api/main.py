"""FastAPI application factory for the Person Validator API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import v1_router
from src.api.schemas import HealthResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Person Validator API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Public health check (no auth required)
    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        """Unauthenticated health check."""
        return {"status": "ok"}

    # Versioned API routes (authenticated)
    app.include_router(v1_router)

    return app


# Module-level app instance for uvicorn (e.g. `uvicorn src.api.main:app`)
app = create_app()
