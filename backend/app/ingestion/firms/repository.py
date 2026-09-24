"""Persistence of FIRMS observations (bulk, idempotent)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.ingestion.firms.parser import FirmsObservation

CHUNK = 5000

_INSERT = text(
    """
    INSERT INTO thermal_observations (
        source_id, source_mode, source_record_key, product, instrument, satellite, satellite_name,
        latitude, longitude, geom, brightness, brightness_2, frp, scan, track,
        acq_date, acq_time, acquired_at, confidence_raw, confidence_level, confidence_pct,
        daynight, version, ingestion_run_id
    )
    SELECT 'nasa_firms', :mode, r.k, r.product, r.instrument, r.sat, r.sat_name,
           r.lat, r.lon, ST_SetSRID(ST_MakePoint(r.lon, r.lat), 4326)::geography,
           r.b1, r.b2, r.frp, r.scan, r.track,
           r.d, r.t, r.ts, r.craw, r.clevel, r.cpct, r.dn, r.ver, :run_id
      FROM unnest(
            CAST(:k AS text[]), CAST(:product AS text[]), CAST(:instrument AS text[]),
            CAST(:sat AS text[]), CAST(:sat_name AS text[]),
            CAST(:lat AS float8[]), CAST(:lon AS float8[]),
            CAST(:b1 AS float8[]), CAST(:b2 AS float8[]), CAST(:frp AS float8[]),
            CAST(:scan AS float8[]), CAST(:track AS float8[]),
            CAST(:d AS date[]), CAST(:t AS text[]), CAST(:ts AS timestamptz[]),
            CAST(:craw AS text[]), CAST(:clevel AS text[]), CAST(:cpct AS int2[]),
            CAST(:dn AS text[]), CAST(:ver AS text[])
           ) AS r(k, product, instrument, sat, sat_name, lat, lon, b1, b2, frp, scan, track,
                  d, t, ts, craw, clevel, cpct, dn, ver)
    ON CONFLICT (source_record_key) DO NOTHING
    RETURNING id
    """
)


def insert_observations(conn: Connection, observations: list[FirmsObservation], *, mode: str, run_id: int) -> int:
    """Insert observations; returns the number of new rows (duplicates are skipped)."""
    inserted = 0
    for start in range(0, len(observations), CHUNK):
        chunk = observations[start : start + CHUNK]
        params = {
            "mode": mode,
            "run_id": run_id,
            "k": [o.source_record_key for o in chunk],
            "product": [o.product for o in chunk],
            "instrument": [o.instrument for o in chunk],
            "sat": [o.satellite for o in chunk],
            "sat_name": [o.satellite_name for o in chunk],
            "lat": [o.latitude for o in chunk],
            "lon": [o.longitude for o in chunk],
            "b1": [o.brightness for o in chunk],
            "b2": [o.brightness_2 for o in chunk],
            "frp": [o.frp for o in chunk],
            "scan": [o.scan for o in chunk],
            "track": [o.track for o in chunk],
            "d": [o.acq_date for o in chunk],
            "t": [o.acq_time for o in chunk],
            "ts": [o.acquired_at for o in chunk],
            "craw": [o.confidence_raw for o in chunk],
            "clevel": [o.confidence_level for o in chunk],
            "cpct": [o.confidence_pct for o in chunk],
            "dn": [o.daynight for o in chunk],
            "ver": [o.version for o in chunk],
        }
        inserted += len(conn.execute(_INSERT, params).fetchall())
    return inserted
