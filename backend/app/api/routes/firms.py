from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.api.deps import parse_bbox, parse_csv_list, require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, Observation
from app.config import FIRMS_PRODUCTS_ALLOWED, get_settings
from app.core.errors import NotFoundError
from app.core.responses import ok
from app.db.engine import connection
from app.repositories.observations import get_observation, list_observations

router = APIRouter(tags=["Thermal observations"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/firms", response_model=ApiResponse[list[Observation]], summary="NASA FIRMS detections")
def get_firms(
    hours: int = Query(48, ge=1, le=24 * 60, description="Look-back window on acquisition time"),
    bbox: str | None = Query(None, description="west,south,east,north"),
    product: str | None = Query(None, description="Comma-separated FIRMS products, e.g. VIIRS_SNPP_NRT"),
    instrument: Literal["VIIRS", "MODIS"] | None = None,
    min_frp: float | None = Query(None, ge=0, description="Minimum fire radiative power (MW)"),
    confidence: Literal["low", "nominal", "high"] | None = Query(None, description="Minimum confidence level"),
    daynight: Literal["D", "N"] | None = None,
    limit: int = Query(500, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Stored, validated FIRMS active-fire detections for the configured region, newest first.
    Every row carries its product, satellite, source mode (API or public feed) and ingestion run."""
    filters = dict(
        hours=hours,
        bbox=parse_bbox(bbox),
        products=parse_csv_list(product, FIRMS_PRODUCTS_ALLOWED, "product"),
        instrument=instrument,
        min_frp=min_frp,
        confidence=confidence,
        daynight=daynight,
    )
    with connection() as conn:
        rows, total = list_observations(conn, limit=limit, offset=offset, **filters)
        last_run = conn.execute(
            text(
                "SELECT id, status, started_at, finished_at, records_valid, records_inserted, params->>'mode' AS mode "
                "FROM ingestion_runs WHERE job = 'firms_ingest' ORDER BY started_at DESC LIMIT 1"
            )
        ).mappings().one_or_none()
    settings = get_settings()
    return ok(
        rows,
        {
            "total": total,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "region": settings.region_name,
            "source": "NASA FIRMS",
            "latest_ingestion": dict(last_run) if last_run else None,
        },
    )


@router.get("/firms/{observation_id}", response_model=ApiResponse[Observation], summary="One FIRMS detection")
def get_firms_observation(observation_id: int):
    with connection() as conn:
        row = get_observation(conn, observation_id)
    if not row:
        raise NotFoundError(f"Observation {observation_id} not found")
    return ok(row)


@router.get("/ingestion-runs", summary="Recent ingestion / analysis runs")
def get_ingestion_runs(
    job: str | None = Query(None, description="firms_ingest | facilities_ingest | analysis"),
    limit: int = Query(20, ge=1, le=200),
):
    with connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, job, source_id, status, started_at, finished_at, records_fetched, records_valid,
                       records_inserted, records_updated, records_rejected, params, details, error
                  FROM ingestion_runs
                 WHERE (CAST(:job AS text) IS NULL OR job = :job)
                 ORDER BY started_at DESC LIMIT :limit
                """
            ),
            {"job": job, "limit": limit},
        ).mappings().all()
    return ok([dict(r) for r in rows], {"count": len(rows)})
