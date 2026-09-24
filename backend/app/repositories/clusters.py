"""Read queries for thermal clusters, their evidence and risk zones."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.intelligence import CLASSIFICATION_LABELS
from app.config import PRIORITY_ORDER
from app.geo.region import BBox
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories.filters import Where, feature_collection, point_feature

_COLUMNS = """
    c.id, c.status, c.center_latitude, c.center_longitude, c.extent_radius_m, c.observation_count,
    c.max_frp, c.avg_frp, c.total_frp, c.max_brightness, c.start_time, c.end_time, c.duration_hours,
    c.detection_days, c.night_fraction, c.mean_confidence, c.instruments, c.products,
    c.persistence_category, c.persistence_detection_days, c.persistence_coverage_days, c.persistence_ratio,
    c.nearest_facility_id, c.nearest_facility_distance_m, c.spatial_relationship, c.industrial_association,
    c.facility_member_share, c.classification, c.evidence_strength, c.risk_score, c.priority,
    c.analysis_version, c.analyzed_at,
    f.name AS facility_name, f.facility_type, f.source_ref AS facility_source_ref,
    lc.dominant_class_name AS land_cover_class, lc.dominant_fraction AS land_cover_fraction,
    i.id AS incident_id
"""

_JOINS = """
    LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id
    LEFT JOIN land_cover lc ON lc.id = c.land_cover_id
    LEFT JOIN incidents i ON i.cluster_id = c.id
"""

SORTS = {
    "risk": "c.risk_score DESC NULLS LAST, c.end_time DESC",
    "recent": "c.end_time DESC",
    "frp": "c.max_frp DESC NULLS LAST",
    "count": "c.observation_count DESC",
}


CONFIDENCE_MIN = {"low": 0.0, "nominal": 0.55, "high": 0.85}


def _where(
    *,
    status: str | None,
    hours: int | None,
    bbox: BBox | None,
    classifications: list[str] | None,
    min_priority: str | None,
    min_score: float | None,
    associated_only: bool,
    min_observations: int | None,
    facility_types: list[str] | None = None,
    persistence: list[str] | None = None,
    confidence: str | None = None,
) -> Where:
    w = Where()
    if facility_types:
        w.add(
            "c.industrial_association AND c.nearest_facility_id IN "
            "(SELECT id FROM industrial_facilities WHERE facility_type = ANY(CAST(:ftypes AS text[])))",
            ftypes=facility_types,
        )
    if persistence:
        w.add("c.persistence_category = ANY(CAST(:pers AS text[]))", pers=persistence)
    if confidence:
        w.add("c.mean_confidence >= :cmin", cmin=CONFIDENCE_MIN[confidence])
    if status:
        w.add("c.status = :status", status=status)
    if hours:
        w.add("c.end_time >= now() - make_interval(hours => :hours)", hours=hours)
    w.bbox("c.geom", bbox)
    if classifications:
        w.add("c.classification = ANY(CAST(:classes AS text[]))", classes=classifications)
    if min_priority:
        w.add("c.priority = ANY(CAST(:prios AS text[]))", prios=PRIORITY_ORDER[PRIORITY_ORDER.index(min_priority) :])
    if min_score is not None:
        w.add("c.risk_score >= :min_score", min_score=min_score)
    if associated_only:
        w.add("c.industrial_association")
    if min_observations:
        w.add("c.observation_count >= :min_obs", min_obs=min_observations)
    return w


def cluster_filter_subquery(**filters) -> tuple[str, dict] | None:
    """`SELECT c.id FROM thermal_clusters c WHERE ...` for cluster-level filters, or None if unfiltered.
    Used to filter detections (hotspots) by the attributes of the event they belong to."""
    keys = ("classifications", "min_priority", "facility_types", "persistence")
    if not any(filters.get(k) for k in keys):
        return None
    w = _where(
        status=None, hours=None, bbox=None, classifications=filters.get("classifications"),
        min_priority=filters.get("min_priority"), min_score=None, associated_only=False, min_observations=None,
        facility_types=filters.get("facility_types"), persistence=filters.get("persistence"), confidence=None,
    )
    return f"SELECT c.id FROM thermal_clusters c {w.sql}", w.params


def _decorate(row: dict) -> dict:
    row["classification_label"] = CLASSIFICATION_LABELS.get(row.get("classification") or "", None)
    if row.get("facility_type"):
        row["facility_type_label"] = FACILITY_TYPES.get(row["facility_type"], row["facility_type"])
    return row


def list_clusters(conn: Connection, *, limit: int, offset: int, sort: str, **filters) -> tuple[list[dict], int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM thermal_clusters c {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM thermal_clusters c {_JOINS} {w.sql} ORDER BY {SORTS[sort]} LIMIT :limit OFFSET :offset"),
        {**w.params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [_decorate(dict(r)) for r in rows], int(total)


def clusters_geojson(conn: Connection, *, limit: int, **filters) -> tuple[dict, int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM thermal_clusters c {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM thermal_clusters c {_JOINS} {w.sql} ORDER BY {SORTS['risk']} LIMIT :limit"),
        {**w.params, "limit": limit},
    ).mappings().all()
    features = []
    for r in rows:
        r = _decorate(dict(r))
        features.append(
            point_feature(
                r["id"],
                r["center_latitude"],
                r["center_longitude"],
                {
                    k: r[k]
                    for k in (
                        "id", "observation_count", "max_frp", "risk_score", "priority", "classification",
                        "classification_label", "persistence_category", "spatial_relationship",
                        "industrial_association", "facility_name", "end_time", "start_time", "incident_id",
                        "extent_radius_m",
                    )
                },
            )
        )
    return feature_collection(features), int(total)


def get_cluster(conn: Connection, cluster_id: int, observation_limit: int = 500) -> dict | None:
    row = conn.execute(
        text(
            f"""
            SELECT {_COLUMNS}, c.intelligence, c.persistence_details, c.merged_into_id,
                   ST_AsGeoJSON(c.hull, 6)::json AS hull,
                   lc.class_fractions AS land_cover_fractions, lc.status AS land_cover_status,
                   lc.sample_radius_m AS land_cover_radius_m, lc.resolution_m AS land_cover_resolution_m,
                   lc.dataset_version AS land_cover_dataset, lc.sampled_at AS land_cover_sampled_at,
                   lc.source_tile AS land_cover_tile
              FROM thermal_clusters c {_JOINS}
             WHERE c.id = :id
            """
        ),
        {"id": cluster_id},
    ).mappings().one_or_none()
    if not row:
        return None
    cluster = _decorate(dict(row))
    cluster["nearby_facilities"] = [
        {**dict(r), "facility_type_label": FACILITY_TYPES.get(r["facility_type"], r["facility_type"])}
        for r in conn.execute(
            text(
                """
                SELECT p.rank, p.distance_m, p.relationship, f.id, f.name, f.facility_type, f.operator,
                       f.source_ref, f.latitude, f.longitude
                  FROM cluster_facility_proximity p JOIN industrial_facilities f ON f.id = p.facility_id
                 WHERE p.cluster_id = :id ORDER BY p.rank
                """
            ),
            {"id": cluster_id},
        ).mappings()
    ]
    cluster["observations"] = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT id, latitude, longitude, frp, brightness, acquired_at, satellite_name, instrument,
                       product, confidence_level, confidence_pct, daynight, source_mode
                  FROM thermal_observations WHERE cluster_id = :id
                 ORDER BY acquired_at DESC LIMIT :lim
                """
            ),
            {"id": cluster_id, "lim": observation_limit},
        ).mappings()
    ]
    return cluster


def risk_zones_geojson(conn: Connection, radius_m: int) -> dict:
    rows = conn.execute(
        text(
            """
            SELECT i.id, i.title, i.priority, i.risk_score, i.classification, i.status, i.cluster_id,
                   ST_AsGeoJSON(ST_Buffer(COALESCE(f.footprint, i.geom), :r, 'quad_segs=4'), 5)::json AS geometry
              FROM incidents i
              LEFT JOIN industrial_facilities f ON f.id = i.facility_id
             WHERE i.status IN ('active', 'monitoring')
            """
        ),
        {"r": radius_m},
    ).mappings().all()
    return feature_collection(
        [
            {
                "type": "Feature",
                "id": r["id"],
                "geometry": r["geometry"],
                "properties": {
                    "incident_id": r["id"],
                    "title": r["title"],
                    "priority": r["priority"],
                    "risk_score": r["risk_score"],
                    "classification": r["classification"],
                    "status": r["status"],
                    "cluster_id": r["cluster_id"],
                    "buffer_m": radius_m,
                },
            }
            for r in rows
        ]
    )
