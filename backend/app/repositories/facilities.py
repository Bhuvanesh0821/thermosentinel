"""Read queries for industrial facilities."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.geo.region import BBox
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories.filters import Where, feature_collection, point_feature

_COLUMNS = """
    f.id, f.source_id, f.source_ref, f.name, f.facility_type, f.facility_subtype, f.operator, f.website,
    f.latitude, f.longitude, f.footprint_area_m2, f.source_timestamp, f.first_seen_at, f.last_seen_at, f.is_active
"""


def _where(*, types: list[str] | None, bbox: BBox | None, q: str | None, active_only: bool = True) -> Where:
    w = Where()
    if active_only:
        w.add("f.is_active")
    if types:
        w.add("f.facility_type = ANY(CAST(:types AS text[]))", types=types)
    w.bbox("f.geom", bbox)
    if q:
        w.add("(f.name ILIKE :q OR f.operator ILIKE :q)", q=f"%{q}%")
    return w


def _decorate(row: dict) -> dict:
    row["facility_type_label"] = FACILITY_TYPES.get(row["facility_type"], row["facility_type"])
    ref = row.get("source_ref") or ""
    row["source_url"] = f"https://www.openstreetmap.org/{ref}" if ref else None
    return row


def list_facilities(conn: Connection, *, limit: int, offset: int, **filters) -> tuple[list[dict], int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM industrial_facilities f {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(
            f"SELECT {_COLUMNS} FROM industrial_facilities f {w.sql} "
            "ORDER BY f.name NULLS LAST, f.id LIMIT :limit OFFSET :offset"
        ),
        {**w.params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [_decorate(dict(r)) for r in rows], int(total)


def facilities_geojson(conn: Connection, *, limit: int, **filters) -> tuple[dict, int]:
    w = _where(**filters)
    total = conn.execute(text(f"SELECT count(*) FROM industrial_facilities f {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(
            f"""
            SELECT f.id, f.name, f.facility_type, f.facility_subtype, f.operator, f.source_ref,
                   f.latitude, f.longitude, f.footprint IS NOT NULL AS has_footprint
              FROM industrial_facilities f {w.sql}
             ORDER BY f.id LIMIT :limit
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
                "name": r["name"],
                "type": r["facility_type"],
                "type_label": FACILITY_TYPES.get(r["facility_type"], r["facility_type"]),
                "subtype": r["facility_subtype"],
                "operator": r["operator"],
                "source_ref": r["source_ref"],
                "has_footprint": r["has_footprint"],
            },
        )
        for r in rows
    ]
    return feature_collection(features), int(total)


def footprints_geojson(conn: Connection, *, bbox: BBox, types: list[str] | None, limit: int) -> dict:
    w = _where(types=types, bbox=None, q=None)
    w.add("f.footprint IS NOT NULL")
    w.bbox("f.footprint", bbox)
    rows = conn.execute(
        text(
            f"""
            SELECT f.id, f.name, f.facility_type, ST_AsGeoJSON(f.footprint, 6)::json AS geometry
              FROM industrial_facilities f {w.sql}
             ORDER BY f.footprint_area_m2 DESC NULLS LAST LIMIT :limit
            """
        ),
        {**w.params, "limit": limit},
    ).mappings().all()
    return feature_collection(
        [
            {
                "type": "Feature",
                "id": r["id"],
                "geometry": r["geometry"],
                "properties": {"id": r["id"], "name": r["name"], "type": r["facility_type"]},
            }
            for r in rows
        ]
    )


def get_facility(conn: Connection, facility_id: int) -> dict | None:
    row = conn.execute(
        text(
            f"SELECT {_COLUMNS}, f.tags, ST_AsGeoJSON(f.footprint, 6)::json AS footprint "
            "FROM industrial_facilities f WHERE f.id = :id"
        ),
        {"id": facility_id},
    ).mappings().one_or_none()
    if not row:
        return None
    facility = _decorate(dict(row))
    facility["related_clusters"] = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT c.id, c.status, c.classification, c.priority, c.risk_score, c.observation_count,
                       c.max_frp, c.end_time, p.distance_m, p.relationship
                  FROM cluster_facility_proximity p
                  JOIN thermal_clusters c ON c.id = p.cluster_id
                 WHERE p.facility_id = :id
                 ORDER BY c.end_time DESC LIMIT 50
                """
            ),
            {"id": facility_id},
        ).mappings()
    ]
    return facility


def type_counts(conn: Connection) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT facility_type, count(*) AS count FROM industrial_facilities WHERE is_active "
            "GROUP BY facility_type ORDER BY count DESC"
        )
    ).mappings().all()
    return [
        {"facility_type": r["facility_type"], "label": FACILITY_TYPES.get(r["facility_type"], r["facility_type"]), "count": r["count"]}
        for r in rows
    ]
