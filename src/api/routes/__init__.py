"""API route modules.

All versioned routes are mounted under /v1/ via the v1_router.
Public routes (no auth) use the health_router.
"""

from src.api.routes.health import health_router
from src.api.routes.v1 import v1_router

__all__ = ["health_router", "v1_router"]
