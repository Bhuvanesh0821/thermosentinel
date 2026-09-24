"""Dashboard summary metrics - every number is a live aggregate over stored data."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.intelligence import CLASSIFICATION_LABELS


def bucket_step(hours: int) -> tuple[str, int]:
    """Bucket width for a look-back window (~24-30 columns)."""
    if hours <= 24:
        return "1 hour", 1
    if hours <= 48:
        return "2 hours", 2
    if hours <= 168:
        return "6 hours", 6
    return "1 day", 24


def timeseries(conn: Connection, hours: int) -> dict:
    """Detections per time bucket (all buckets present, zero-filled). Buckets that start
    before the earliest stored detection are flagged `covered=false`: no data is held for
    them, which is different from zero detections."""
    step, step_hours = bucket_step(hours)
    rows = conn.execute(
        text(
            """
            WITH buckets AS (
                SELECT generate_series(
                           date_bin(CAST(:step AS interval), now() - make_interval(hours => :h), TIMESTAMPTZ '2000-01-01 00:00:00+00'),
                           date_bin(CAST(:step AS interval), now(), TIMESTAMPTZ '2000-01-01 00:00:00+00'),
                           CAST(:step AS interval)) AS bucket
            ),
            obs AS (
                SELECT date_bin(CAST(:step AS interval), acquired_at, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS bucket,
                       count(*) AS total,
                       count(*) FILTER (WHERE daynight = 'N') AS night,
                       count(*) FILTER (WHERE instrument = 'VIIRS') AS viirs,
                       count(*) FILTER (WHERE instrument = 'MODIS') AS modis,
                       max(frp) AS max_frp
                  FROM thermal_observations
                 WHERE acquired_at >= now() - make_interval(hours => :h)
                 GROUP BY 1
            )
            SELECT b.bucket, coalesce(o.total, 0) AS total, coalesce(o.night, 0) AS night,
                   coalesce(o.viirs, 0) AS viirs, coalesce(o.modis, 0) AS modis, o.max_frp
              FROM buckets b LEFT JOIN obs o USING (bucket)
             ORDER BY b.bucket
            """
        ),
        {"step": step, "h": hours},
    ).mappings().all()
    earliest = conn.execute(text("SELECT min(acquired_at) FROM thermal_observations")).scalar_one()
    buckets = []
    for r in rows:
        item = dict(r)
        item["day"] = item["total"] - item["night"]
        # A bucket is "covered" once stored history has begun (the bucket end is after the first detection).
        item["covered"] = earliest is not None and r["bucket"].timestamp() + step_hours * 3600 > earliest.timestamp()
        buckets.append(item)
    return {"window_hours": hours, "bucket": step, "bucket_hours": step_hours, "earliest_detection": earliest, "buckets": buckets}


def summary(conn: Connection, hours: int) -> dict:
    obs = conn.execute(
        text(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE instrument = 'VIIRS') AS viirs,
                   count(*) FILTER (WHERE instrument = 'MODIS') AS modis,
                   count(*) FILTER (WHERE daynight = 'N') AS night,
                   max(frp) AS max_frp,
                   max(acquired_at) AS latest_acquisition,
                   min(acquired_at) AS earliest_acquisition
              FROM thermal_observations
             WHERE acquired_at >= now() - make_interval(hours => :h)
            """
        ),
        {"h": hours},
    ).mappings().one()
    stored = conn.execute(
        text("SELECT count(*) AS total, min(acq_date) AS first_day, max(acq_date) AS last_day FROM thermal_observations")
    ).mappings().one()
    clusters = conn.execute(
        text(
            """
            SELECT count(*) AS active,
                   count(*) FILTER (WHERE industrial_association) AS industrial_associated,
                   count(*) FILTER (WHERE persistence_category = 'persistent') AS persistent,
                   count(*) FILTER (WHERE observation_count > 1) AS multi_detection
              FROM thermal_clusters
             WHERE status = 'active' AND end_time >= now() - make_interval(hours => :h)
            """
        ),
        {"h": hours},
    ).mappings().one()
    classes = conn.execute(
        text(
            """
            SELECT classification, count(*) AS count FROM thermal_clusters
             WHERE status = 'active' AND end_time >= now() - make_interval(hours => :h) AND classification IS NOT NULL
             GROUP BY classification ORDER BY count DESC
            """
        ),
        {"h": hours},
    ).mappings().all()
    incidents = conn.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE status = 'active') AS active,
                   count(*) FILTER (WHERE status = 'monitoring') AS monitoring,
                   count(*) FILTER (WHERE status IN ('active', 'monitoring') AND priority = 'critical') AS critical,
                   count(*) FILTER (WHERE status IN ('active', 'monitoring') AND priority = 'high') AS high,
                   count(*) FILTER (WHERE status IN ('active', 'monitoring') AND priority = 'medium') AS medium,
                   count(*) FILTER (WHERE status IN ('active', 'monitoring') AND priority = 'low') AS low
              FROM incidents
            """
        )
    ).mappings().one()
    alerts = conn.execute(
        text(
            "SELECT count(*) FILTER (WHERE status = 'open') AS open, "
            "count(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS last_24h FROM alerts"
        )
    ).mappings().one()
    facilities = conn.execute(text("SELECT count(*) FROM industrial_facilities WHERE is_active")).scalar_one()
    last_runs = {
        r["job"]: dict(r)
        for r in conn.execute(
            text(
                """
                SELECT DISTINCT ON (job) job, status, started_at, finished_at, records_inserted, records_valid
                  FROM ingestion_runs ORDER BY job, started_at DESC
                """
            )
        ).mappings()
    }
    return {
        "window_hours": hours,
        "detections": dict(obs),
        "stored_detections": dict(stored),
        "clusters": dict(clusters),
        "classifications": [
            {**dict(r), "label": CLASSIFICATION_LABELS.get(r["classification"], r["classification"])} for r in classes
        ],
        "incidents": dict(incidents),
        "alerts": dict(alerts),
        "facilities": int(facilities),
        "last_runs": last_runs,
    }
