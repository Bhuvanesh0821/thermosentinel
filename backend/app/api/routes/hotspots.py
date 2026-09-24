from typing import Literal

from fastapi import APIRouter, Depends, Query
from app.core.cache import cached_ok

from app.analytics.classifier import CLASSES
from app.api.deps import parse_bbox, parse_csv_list, require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, FeatureCollection
from app.core.responses import ok
from app.db.engine import connection
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories.clusters import cluster_filter_subquery
from app.repositories.observations import hotspots_geojson

router = APIRouter(tags=["Map layers"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)

PERSISTENCE = {"persistent", "recurring", "transient", "insufficient_history"}


@router.get("/hotspots", response_model=ApiResponse[FeatureCollection], summary="Thermal detections (GeoJSON)")
def get_hotspots(
    hours: int = Query(48, ge=1, le=24 * 60),
    bbox: str | None = Query(None, description="west,south,east,north"),
    min_frp: float | None = Query(None, ge=0),
    confidence: Literal["low", "nominal", "high"] | None = None,
    instrument: Literal["VIIRS", "MODIS"] | None = None,
    daynight: Literal["D", "N"] | None = None,
    classification: str | None = Query(None, description="Event classes (comma-separated) of the parent cluster"),
    facility_type: str | None = Query(None, description="Facility types (comma-separated) linked to the parent cluster"),
    persistence: str | None = Query(None, description="Persistence categories (comma-separated)"),
    min_priority: Literal["low", "medium", "high", "critical"] | None = None,
    limit: int = Query(20000, ge=1, le=50000),
):
    """Map layer of FIRMS detections with their cluster assignment and classification. Event-level
    filters (classification, facility type, persistence, priority) select detections whose cluster
    matches. When more detections match than `limit`, the most intense are returned (`meta.truncated`)."""
    cluster_filter = cluster_filter_subquery(
        classifications=parse_csv_list(classification, set(CLASSES), "classification"),
        facility_types=parse_csv_list(facility_type, set(FACILITY_TYPES), "facility type"),
        persistence=parse_csv_list(persistence, PERSISTENCE, "persistence"),
        min_priority=min_priority,
    )
    parsed_bbox = parse_bbox(bbox)

    def build():
        with connection() as conn:
            fc, total = hotspots_geojson(
                conn,
                limit=limit,
                hours=hours,
                bbox=parsed_bbox,
                products=None,
                instrument=instrument,
                min_frp=min_frp,
                confidence=confidence,
                daynight=daynight,
                cluster_filter=cluster_filter,
            )
        return fc, {"total": total, "count": len(fc["features"]), "truncated": total > len(fc["features"]), "hours": hours}

    params = dict(hours=hours, bbox=bbox, min_frp=min_frp, confidence=confidence, instrument=instrument, daynight=daynight,
                  classification=classification, facility_type=facility_type, persistence=persistence,
                  min_priority=min_priority, limit=limit)
    return cached_ok("hotspots", params, build)
