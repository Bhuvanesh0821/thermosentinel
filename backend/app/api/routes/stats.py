from fastapi import APIRouter, Depends, Query

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.responses import ok
from app.db.engine import connection
from app.repositories.stats import summary, timeseries

router = APIRouter(tags=["System"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/stats/summary", summary="Dashboard metrics")
def get_summary(hours: int = Query(24, ge=1, le=24 * 60)):
    """Live aggregates for the dashboard: detections, clusters, classifications, incidents,
    alerts, facilities and the latest run of each pipeline job."""
    with connection() as conn:
        return ok(summary(conn, hours))


@router.get("/stats/timeseries", summary="Detections per time bucket")
def get_timeseries(hours: int = Query(48, ge=1, le=24 * 60)):
    """Zero-filled detection counts per bucket (1 h for 24 h windows ... 1 day for 30 d),
    split day/night and VIIRS/MODIS. Buckets before the first stored detection are marked
    `covered: false` (no data held, not zero detections)."""
    with connection() as conn:
        return ok(timeseries(conn, hours))
