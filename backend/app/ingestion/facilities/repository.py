"""Persistence of industrial facilities (bulk upsert keyed on OSM element id)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

CHUNK = 1000


@dataclass
class FacilityRecord:
    source_ref: str
    name: str | None
    facility_type: str
    facility_subtype: str | None
    operator: str | None
    website: str | None
    latitude: float
    longitude: float
    footprint_wkt: str | None
    tags: dict


_UPSERT = text(
    """
    INSERT INTO industrial_facilities (
        source_id, source_ref, name, facility_type, facility_subtype, operator, website,
        latitude, longitude, geom, footprint, footprint_area_m2, tags, source_timestamp,
        ingestion_run_id, is_active, last_seen_at
    )
    SELECT 'osm_overpass', r.ref, r.name, r.ftype, r.fsub, r.operator, r.website,
           r.lat, r.lon, ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326)::geography,
           CASE WHEN r.wkt IS NULL THEN NULL ELSE ST_GeogFromText(r.wkt) END,
           CASE WHEN r.wkt IS NULL THEN NULL ELSE ST_Area(ST_GeogFromText(r.wkt)) END,
           CAST(r.tags AS jsonb), CAST(:source_ts AS timestamptz), :run_id, true, now()
      FROM unnest(
            CAST(:ref AS text[]), CAST(:name AS text[]), CAST(:ftype AS text[]), CAST(:fsub AS text[]),
            CAST(:operator AS text[]), CAST(:website AS text[]),
            CAST(:lat AS float8[]), CAST(:lon AS float8[]), CAST(:wkt AS text[]), CAST(:tags AS text[])
           ) AS r(ref, name, ftype, fsub, operator, website, lat, lon, wkt, tags)
    ON CONFLICT (source_id, source_ref) DO UPDATE SET
        name = EXCLUDED.name,
        facility_type = EXCLUDED.facility_type,
        facility_subtype = EXCLUDED.facility_subtype,
        operator = EXCLUDED.operator,
        website = EXCLUDED.website,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        geom = EXCLUDED.geom,
        footprint = EXCLUDED.footprint,
        footprint_area_m2 = EXCLUDED.footprint_area_m2,
        tags = EXCLUDED.tags,
        source_timestamp = EXCLUDED.source_timestamp,
        ingestion_run_id = EXCLUDED.ingestion_run_id,
        is_active = true,
        last_seen_at = now()
    RETURNING (xmax = 0) AS inserted
    """
)


def upsert_facilities(
    conn: Connection, records: list[FacilityRecord], *, run_id: int, source_timestamp: str | None
) -> tuple[int, int]:
    """Returns (inserted, updated)."""
    inserted = updated = 0
    for start in range(0, len(records), CHUNK):
        chunk = records[start : start + CHUNK]
        rows = conn.execute(
            _UPSERT,
            {
                "run_id": run_id,
                "source_ts": source_timestamp,
                "ref": [r.source_ref for r in chunk],
                "name": [r.name for r in chunk],
                "ftype": [r.facility_type for r in chunk],
                "fsub": [r.facility_subtype for r in chunk],
                "operator": [r.operator for r in chunk],
                "website": [r.website for r in chunk],
                "lat": [r.latitude for r in chunk],
                "lon": [r.longitude for r in chunk],
                "wkt": [r.footprint_wkt for r in chunk],
                "tags": [json.dumps(r.tags, ensure_ascii=False) for r in chunk],
            },
        ).fetchall()
        for (was_inserted,) in rows:
            if was_inserted:
                inserted += 1
            else:
                updated += 1
    return inserted, updated
