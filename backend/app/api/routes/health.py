from fastapi import APIRouter

from app.api.schemas import ApiResponse, Health
from app.core.responses import ok
from app.health.service import health

router = APIRouter(tags=["System"])


@router.get("/health", response_model=ApiResponse[Health], summary="System health")
def get_health():
    """Live health: database connectivity (with latency and PostGIS version), FIRMS access mode,
    scheduler jobs and pipeline state. Always answers, even when the database is down."""
    return ok(health())
