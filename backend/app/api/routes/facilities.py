from typing import Literal

from fastapi import APIRouter, Depends, Query
from app.core.cache import cached_ok

from app.api.deps import parse_bbox, parse_csv_list, require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, Facility, FeatureCollection
from app.core.errors import BadRequestError, NotFoundError
from app.core.responses import ok
from app.db.engine import connection
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories import facilities as repo

router = APIRouter(tags=["Industrial facilities"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)

FACILITY_TYPE_SET = set(FACILITY_TYPES)


@router.get("/facilities", response_model=ApiResponse[list[Facility]] | ApiResponse[FeatureCollection], summary="Industrial facilities")
def get_facilities(
    type: str | None = Query(None, description="Comma-separated facility types"),
    bbox: str | None = Query(None, description="west,south,east,north"),
    q: str | None = Query(None, min_length=2, max_length=100, description="Search name or operator"),
    format: Literal["json", "geojson"] = "json",
    limit: int = Query(200, ge=1, le=20000),
    offset: int = Query(0, ge=0),
):
    """Facilities from OpenStreetMap with a thermally relevant industrial role. `format=geojson`
    returns a point layer for the map."""
    filters = dict(types=parse_csv_list(type, FACILITY_TYPE_SET, "facility type"), bbox=parse_bbox(bbox), q=q)
    if format == "geojson":

        def build():
            with connection() as conn:
                fc, total = repo.facilities_geojson(conn, limit=limit, **filters)
            return fc, {"total": total, "count": len(fc["features"]), "truncated": total > len(fc["features"])}

        return cached_ok("facilities", dict(type=type, bbox=bbox, q=q, limit=limit), build)
    with connection() as conn:
        rows, total = repo.list_facilities(conn, limit=limit, offset=offset, **filters)
    return ok(rows, {"total": total, "count": len(rows), "limit": limit, "offset": offset, "attribution": "(c) OpenStreetMap contributors (ODbL)"})


@router.get("/facilities/types", summary="Facility type counts")
def get_facility_types():
    with connection() as conn:
        counts = {r["facility_type"]: r for r in repo.type_counts(conn)}
    data = [
        {"facility_type": key, "label": label, "count": counts.get(key, {}).get("count", 0)}
        for key, label in FACILITY_TYPES.items()
    ]
    return ok(data, {"total": sum(d["count"] for d in data)})


@router.get("/facilities/footprints", response_model=ApiResponse[FeatureCollection], summary="Facility outlines (GeoJSON)")
def get_footprints(
    bbox: str = Query(..., description="west,south,east,north - required; keep to the visible map extent"),
    type: str | None = None,
    limit: int = Query(2000, ge=1, le=5000),
):
    box = parse_bbox(bbox)
    if (box.east - box.west) * (box.north - box.south) > 64:
        raise BadRequestError("bbox too large for footprints; zoom in (max 64 square degrees).")
    with connection() as conn:
        fc = repo.footprints_geojson(conn, bbox=box, types=parse_csv_list(type, FACILITY_TYPE_SET, "facility type"), limit=limit)
    return ok(fc, {"count": len(fc["features"])})


@router.get("/facilities/{facility_id}", summary="Facility detail")
def get_facility(facility_id: int):
    with connection() as conn:
        facility = repo.get_facility(conn, facility_id)
    if not facility:
        raise NotFoundError(f"Facility {facility_id} not found")
    return ok(facility)
