"""Read queries for thermal observations (FIRMS detections)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.geo.region import BBox
from app.repositories.filters import Where, feature_collection, point_feature

CONFIDENCE_AT_LEAST = {
    "low": ["low", "nominal", "high"],
    "nominal": ["nominal", "high"],
    "high": ["high"],
}

_COLUMNS = """
    o.id, o.source_id, o.source_mode, o.product, o.instrument, o.satellite, o.satellite_name,
    o.latitude, o.longitude, o.brightness, o.brightness_2, o.frp, o.scan, o.track,
    o.acq_date, o.acq_time, o.acquired_at, o.confidence_raw, o.confidence_level, o.confidence_pct,
    o.daynight, o.version, o.cluster_id, o.ingestion_run_id, o.ingested_at
"""


def _where(
    *,
    hours: int | None,
    bbox: BBox | None,
    products: list[str] | None,
    instrument: str | None,
    min_frp: float | None,
    confidence: str | None,
    daynight: str | None,
    cluster_filter: tuple[str, dict] | None = None,
) -> Where:
    w = Where()
    if cluster_filter:
        sub, params = cluster_filter
        w.add(f"o.cluster_id IN ({sub})", **params)
    if hours:
        w.add("o.acquired_at >= now() - make_interval(hours => :hours)", hours=hours)
    w.bbox("o.geom", bbox)
    if products:
        w.add("o.product = ANY(CAST(:products AS text[]))", products=products)
    if instrument:
        w.add("o.instrument = :instrument", instrument=instrument)
    if min_frp is not None:
        w.add("o.frp >= :min_frp", min_frp=min_frp)
    if confidence:
        w.add("o.confidence_level = ANY(CAST(:conf AS text[]))", conf=CONFIDENCE_AT_LEAST[confidence])
    if daynight:
        w.add("o.daynight = :dn", dn=daynight)
    return w


def list_observations(conn: Connection, *, limit: int, offset: int, **filters) -> tuple[list[dict], int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM thermal_observations o {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM thermal_observations o {w.sql} ORDER BY o.acquired_at DESC, o.id DESC LIMIT :limit OFFSET :offset"),
        {**w.params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows], int(total)


def hotspots_geojson(conn: Connection, *, limit: int, **filters) -> tuple[dict, int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM thermal_observations o {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(
            f"""
            SELECT o.id, o.latitude, o.longitude, o.frp, o.brightness, o.acquired_at, o.satellite_name,
                   o.instrument, o.product, o.confidence_level, o.confidence_pct, o.daynight, o.cluster_id,
                   c.classification, c.priority
              FROM thermal_observations o
              LEFT JOIN thermal_clusters c ON c.id = o.cluster_id
              {w.sql}
             ORDER BY o.frp DESC NULLS LAST
             LIMIT :limit
            """
        ),
        {**w.params, "limit": limit},
    ).mappings().all()
    features = [
        point_feature(
            r["id"],
            r["latitude"],
            r["longitude"],
            {
                "id": r["id"],
                "frp": r["frp"],
                "brightness": r["brightness"],
                "acquired_at": r["acquired_at"],
                "satellite": r["satellite_name"],
                "instrument": r["instrument"],
                "product": r["product"],
                "confidence": r["confidence_level"],
                "confidence_pct": r["confidence_pct"],
                "daynight": r["daynight"],
                "cluster_id": r["cluster_id"],
                "classification": r["classification"],
                "priority": r["priority"],
            },
        )
        for r in rows
    ]
    return feature_collection(features), int(total)


def get_observation(conn: Connection, observation_id: int) -> dict | None:
    row = conn.execute(
        text(f"SELECT {_COLUMNS} FROM thermal_observations o WHERE o.id = :id"), {"id": observation_id}
    ).mappings().one_or_none()
    return dict(row) if row else None
