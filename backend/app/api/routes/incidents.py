from typing import Literal

from fastapi import APIRouter, Depends, Query
from app.core.cache import cached_ok

from app.analytics.classifier import CLASSES
from app.api.deps import parse_bbox, parse_csv_list, require_db
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.api.schemas import ERROR_RESPONSES, ApiResponse, FeatureCollection, Incident
from app.core.errors import NotFoundError
from app.core.responses import ok
from app.db.engine import connection, transaction
from app.repositories import incidents as repo

router = APIRouter(tags=["Incidents"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)

STATUSES = {"active", "monitoring", "closed"}


@router.get("/incidents", response_model=ApiResponse[list[Incident]] | ApiResponse[FeatureCollection], summary="Incidents")
def get_incidents(
    status: str | None = Query("active,monitoring", description="Comma-separated: active, monitoring, closed"),
    min_priority: Literal["low", "medium", "high", "critical"] | None = None,
    classification: str | None = Query(None, description="Comma-separated event classes"),
    facility_type: str | None = Query(None, description="Comma-separated facility types"),
    persistence: str | None = Query(None, description="Comma-separated persistence categories"),
    hours: int | None = Query(None, ge=1, le=24 * 60, description="Last detection within this window"),
    bbox: str | None = Query(None, description="west,south,east,north"),
    q: str | None = Query(None, min_length=2, max_length=100),
    format: Literal["json", "geojson"] = "json",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    statuses = parse_csv_list(status, STATUSES, "status")
    filters = dict(
        classifications=parse_csv_list(classification, set(CLASSES), "classification"),
        facility_types=parse_csv_list(facility_type, set(FACILITY_TYPES), "facility type"),
        persistence=parse_csv_list(persistence, {"persistent", "recurring", "transient", "insufficient_history"}, "persistence"),
        hours=hours,
        bbox=parse_bbox(bbox),
        q=q,
    )
    if format == "geojson":

        def build():
            with connection() as conn:
                fc = repo.incidents_geojson(conn, statuses=statuses, min_priority=min_priority, **filters)
            return fc, {"count": len(fc["features"])}

        return cached_ok("incidents", dict(filters, bbox=bbox, statuses=statuses, min_priority=min_priority), build)
    with connection() as conn:
        rows, total = repo.list_incidents(conn, statuses=statuses, min_priority=min_priority, limit=limit, offset=offset, **filters)
    return ok(rows, {"total": total, "count": len(rows), "limit": limit, "offset": offset})


@router.get("/incidents/{incident_id}", summary="Incident detail")
def get_incident(incident_id: int):
    with connection() as conn:
        incident = repo.get_incident(conn, incident_id)
    if not incident:
        raise NotFoundError(f"Incident {incident_id} not found")
    return ok(incident)


@router.post("/incidents/{incident_id}/acknowledge", summary="Acknowledge an incident")
def acknowledge_incident(incident_id: int):
    with transaction() as conn:
        row = repo.acknowledge_incident(conn, incident_id)
    if not row:
        raise NotFoundError(f"Incident {incident_id} not found")
    return ok(row)
