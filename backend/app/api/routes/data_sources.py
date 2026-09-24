from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import require_db
from app.api.schemas import ApiResponse, DataSource
from app.core.responses import ok
from app.db.engine import connection
from app.health.service import data_sources

router = APIRouter(tags=["System"])


@router.get("/data-sources", response_model=ApiResponse[list[DataSource]], summary="Data source status and provenance")
def get_data_sources():
    """Status, provenance and licensing of every external source plus the database itself.
    Answers even when the database is down (runtime status then shows as unknown)."""
    return ok(data_sources())


@router.get("/system-events", summary="Recent system events")
def get_system_events(limit: int = Query(50, ge=1, le=500), severity: str | None = None):
    require_db()
    with connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, event_type, severity, source, message, details, created_at
                  FROM system_events
                 WHERE (CAST(:sev AS text) IS NULL OR severity = :sev)
                 ORDER BY created_at DESC LIMIT :limit
                """
            ),
            {"limit": limit, "sev": severity},
        ).mappings().all()
    return ok([dict(r) for r in rows], {"count": len(rows)})
