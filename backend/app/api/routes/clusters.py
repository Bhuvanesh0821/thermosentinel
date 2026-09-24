from typing import Literal

from fastapi import APIRouter, Depends, Query
from app.core.cache import cached_ok

from app.analytics.intelligence import CLASSIFICATION_LABELS
from app.api.deps import parse_bbox, parse_csv_list, require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, Cluster, FeatureCollection
from app.config import get_settings
from app.core.errors import NotFoundError
from app.core.responses import ok
from app.db.engine import connection
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories import clusters as repo

router = APIRouter(tags=["Thermal clusters"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)

Priority = Literal["low", "medium", "high", "critical"]


PERSISTENCE = {"persistent", "recurring", "transient", "insufficient_history"}


def _filters(status, hours, bbox, classification, min_priority, min_score, associated_only, min_observations,
             facility_type=None, persistence=None, confidence=None):
    return dict(
        status=None if status == "all" else status,
        hours=hours,
        bbox=parse_bbox(bbox),
        classifications=parse_csv_list(classification, set(CLASSIFICATION_LABELS), "classification"),
        min_priority=min_priority,
        min_score=min_score,
        associated_only=associated_only,
        min_observations=min_observations,
        facility_types=parse_csv_list(facility_type, set(FACILITY_TYPES), "facility type"),
        persistence=parse_csv_list(persistence, PERSISTENCE, "persistence"),
        confidence=confidence,
    )


@router.get("/clusters", response_model=ApiResponse[list[Cluster]] | ApiResponse[FeatureCollection], summary="Thermal clusters")
def get_clusters(
    status: Literal["active", "inactive", "merged", "all"] = "active",
    hours: int | None = Query(None, ge=1, le=24 * 60, description="Only clusters with a detection in this window"),
    bbox: str | None = None,
    classification: str | None = Query(None, description="Comma-separated classifications"),
    min_priority: Priority | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    associated_only: bool = False,
    min_observations: int | None = Query(None, ge=1),
    facility_type: str | None = Query(None, description="Comma-separated facility types of the associated facility"),
    persistence: str | None = Query(None, description="Comma-separated: persistent, recurring, transient, insufficient_history"),
    confidence: Literal["low", "nominal", "high"] | None = Query(None, description="Minimum mean detection confidence"),
    sort: Literal["risk", "recent", "frp", "count"] = "risk",
    format: Literal["json", "geojson"] = "json",
    limit: int = Query(100, ge=1, le=20000),
    offset: int = Query(0, ge=0),
):
    """Spatio-temporal clusters of real FIRMS detections with persistence, industrial proximity,
    land-cover context and the explainable intelligence assessment."""
    filters = _filters(status, hours, bbox, classification, min_priority, min_score, associated_only, min_observations,
                       facility_type, persistence, confidence)
    if format == "geojson":

        def build():
            with connection() as conn:
                fc, total = repo.clusters_geojson(conn, limit=limit, **filters)
            return fc, {"total": total, "count": len(fc["features"]), "truncated": total > len(fc["features"])}

        return cached_ok("clusters", dict(filters, bbox=bbox, limit=limit), build)
    with connection() as conn:
        rows, total = repo.list_clusters(conn, limit=limit, offset=offset, sort=sort, **filters)
    return ok(rows, {"total": total, "count": len(rows), "limit": limit, "offset": offset})


@router.get("/clusters/{cluster_id}/intelligence", summary="Explainable intelligence profile")
def get_cluster_intelligence(cluster_id: int):
    """`intelligence_score`, `risk_level`, classification (with rationale and rejected alternatives),
    contributing factors and evidence - all computed from this event's real observations."""
    with connection() as conn:
        cluster = repo.get_cluster(conn, cluster_id, observation_limit=1)
    if not cluster:
        raise NotFoundError(f"Cluster {cluster_id} not found")
    intel = cluster.get("intelligence") or {}
    return ok({"cluster_id": cluster_id, **intel})


@router.get("/clusters/{cluster_id}", summary="Cluster detail with evidence")
def get_cluster(cluster_id: int, observation_limit: int = Query(500, ge=1, le=5000)):
    """Full evidence for one cluster: member detections, nearest facilities (top 3), land-cover
    sample, persistence history and the factor-by-factor intelligence breakdown."""
    with connection() as conn:
        cluster = repo.get_cluster(conn, cluster_id, observation_limit)
    if not cluster:
        raise NotFoundError(f"Cluster {cluster_id} not found")
    return ok(cluster)


@router.get("/risk-zones", response_model=ApiResponse[FeatureCollection], summary="Risk zones (GeoJSON)")
def get_risk_zones():
    """Association buffers (PROXIMITY_ASSOC_M) around the facility footprint - or the detection
    point when no facility is linked - of every active/monitoring incident."""
    radius = get_settings().proximity_assoc_m

    def build():
        with connection() as conn:
            fc = repo.risk_zones_geojson(conn, radius)
        return fc, {"count": len(fc["features"]), "buffer_m": radius}

    return cached_ok("risk_zones", {"r": radius}, build)
