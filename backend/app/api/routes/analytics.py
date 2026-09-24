from fastapi import APIRouter, Depends, Query

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.cache import cached_ok
from app.core.responses import ok
from app.db.engine import connection
from app.repositories import analytics as repo

router = APIRouter(tags=["Analytics"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/analytics/overview", summary="Analytics series (real data)")
def get_overview(days: int = Query(30, ge=1, le=365)):
    """Daily detections (day/night, sensor, industrial share, FRP median/p90/max), incidents by
    first-detection day and priority, persistence and classification mix, facility-type
    distribution and top persistent sources. Days with no stored FIRMS data are flagged."""
    def build():
        with connection() as conn:
            return repo.overview(conn, days), None

    return cached_ok("analytics_overview", {"days": days}, build)


@router.get("/analytics/grid", summary="Geographic distribution (GeoJSON grid)")
def get_grid(days: int = Query(30, ge=1, le=365), cell: float = Query(0.5, ge=0.1, le=2.0)):
    """Detections binned into `cell` x `cell` degree squares across India."""
    def build():
        with connection() as conn:
            fc = repo.grid(conn, days, cell)
        return fc, {"cells": len(fc["features"]), "cell_deg": cell, "days": days}

    return cached_ok("analytics_grid", {"days": days, "cell": cell}, build)
