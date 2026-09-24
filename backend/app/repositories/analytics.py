"""Analytics aggregates - every series is computed from stored real data.

Daily series are zero-filled over the requested window; days before the first stored
detection are flagged `covered: false` (no data held - different from zero activity).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.classifier import CLASSES
from app.ingestion.facilities.classify import FACILITY_TYPES

INDUSTRIAL = ("gas_flare_like", "mining_associated", "persistent_industrial_source", "industrial_associated_event")


def overview(conn: Connection, days: int) -> dict:
    p = {"d": days}
    earliest = conn.execute(text("SELECT min(acq_date) FROM thermal_observations")).scalar_one()

    observations = [
        dict(r)
        for r in conn.execute(
            text(
                """
                WITH days AS (
                    SELECT generate_series((now() AT TIME ZONE 'UTC')::date - (:d - 1), (now() AT TIME ZONE 'UTC')::date, interval '1 day')::date AS day
                ), o AS (
                    SELECT o.acq_date AS day, count(*) AS total,
                           count(*) FILTER (WHERE o.daynight = 'N') AS night,
                           count(*) FILTER (WHERE o.instrument = 'VIIRS') AS viirs,
                           count(*) FILTER (WHERE o.instrument = 'MODIS') AS modis,
                           count(*) FILTER (WHERE c.industrial_association) AS industrial,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY o.frp) AS frp_median,
                           percentile_cont(0.9) WITHIN GROUP (ORDER BY o.frp) AS frp_p90,
                           max(o.frp) AS frp_max
                      FROM thermal_observations o
                      LEFT JOIN thermal_clusters c ON c.id = o.cluster_id
                     WHERE o.acq_date > (now() AT TIME ZONE 'UTC')::date - :d
                     GROUP BY o.acq_date
                )
                SELECT d.day, coalesce(o.total, 0) AS total, coalesce(o.night, 0) AS night,
                       coalesce(o.total, 0) - coalesce(o.night, 0) AS day_count, coalesce(o.viirs, 0) AS viirs,
                       coalesce(o.modis, 0) AS modis, coalesce(o.industrial, 0) AS industrial,
                       o.frp_median, o.frp_p90, o.frp_max
                  FROM days d LEFT JOIN o USING (day) ORDER BY d.day
                """
            ),
            p,
        ).mappings()
    ]
    for row in observations:
        row["covered"] = earliest is not None and row["day"] >= earliest

    incidents = [
        dict(r)
        for r in conn.execute(
            text(
                """
                WITH days AS (
                    SELECT generate_series((now() AT TIME ZONE 'UTC')::date - (:d - 1), (now() AT TIME ZONE 'UTC')::date, interval '1 day')::date AS day
                )
                SELECT d.day,
                       count(i.id) FILTER (WHERE i.priority = 'critical') AS critical,
                       count(i.id) FILTER (WHERE i.priority = 'high') AS high,
                       count(i.id) FILTER (WHERE i.priority = 'medium') AS medium,
                       count(i.id) FILTER (WHERE i.priority = 'low') AS low,
                       count(i.id) AS total
                  FROM days d
                  LEFT JOIN incidents i ON (i.first_detected_at AT TIME ZONE 'UTC')::date = d.day
                 GROUP BY d.day ORDER BY d.day
                """
            ),
            p,
        ).mappings()
    ]
    for row in incidents:
        row["covered"] = earliest is not None and row["day"] >= earliest

    persistence = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT persistence_category AS category, count(*) AS clusters,
                       count(*) FILTER (WHERE industrial_association) AS industrial
                  FROM thermal_clusters
                 WHERE status = 'active' AND persistence_category IS NOT NULL
                 GROUP BY 1
                """
            )
        ).mappings()
    ]
    classifications = [
        {**dict(r), "label": CLASSES.get(r["classification"], r["classification"])}
        for r in conn.execute(
            text(
                """
                SELECT classification, count(*) AS clusters, sum(observation_count) AS detections
                  FROM thermal_clusters WHERE status = 'active' AND classification IS NOT NULL
                 GROUP BY 1 ORDER BY clusters DESC
                """
            )
        ).mappings()
    ]
    facility_types = [
        {**dict(r), "label": FACILITY_TYPES.get(r["facility_type"], r["facility_type"])}
        for r in conn.execute(
            text(
                """
                SELECT f.facility_type, count(DISTINCT c.id) AS clusters, sum(c.observation_count) AS detections,
                       count(DISTINCT f.id) AS facilities
                  FROM thermal_clusters c JOIN industrial_facilities f ON f.id = c.nearest_facility_id
                 WHERE c.status = 'active' AND c.industrial_association
                 GROUP BY f.facility_type ORDER BY detections DESC
                """
            )
        ).mappings()
    ]
    top_sources = [
        {**dict(r), "classification_label": CLASSES.get(r["classification"], r["classification"]),
         "facility_type_label": FACILITY_TYPES.get(r["facility_type"] or "", None)}
        for r in conn.execute(
            text(
                """
                SELECT c.id AS cluster_id, c.classification, c.persistence_detection_days, c.persistence_coverage_days,
                       c.observation_count, c.max_frp, c.risk_score, c.center_latitude, c.center_longitude,
                       f.name AS facility_name, f.facility_type, i.id AS incident_id
                  FROM thermal_clusters c
                  LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id AND c.industrial_association
                  LEFT JOIN incidents i ON i.cluster_id = c.id
                 WHERE c.status = 'active' AND c.persistence_category = 'persistent'
                 ORDER BY c.persistence_detection_days DESC, c.observation_count DESC
                 LIMIT 10
                """
            )
        ).mappings()
    ]
    totals = conn.execute(
        text(
            """
            SELECT (SELECT count(*) FROM thermal_observations WHERE acq_date > (now() AT TIME ZONE 'UTC')::date - :d) AS detections,
                   (SELECT count(*) FROM thermal_clusters WHERE status = 'active') AS active_clusters,
                   (SELECT count(*) FROM thermal_clusters WHERE status = 'active' AND industrial_association) AS industrial_clusters,
                   (SELECT count(*) FROM thermal_clusters WHERE status = 'active' AND persistence_category = 'persistent') AS persistent_sources,
                   (SELECT count(*) FROM incidents WHERE status IN ('active', 'monitoring')) AS open_incidents,
                   (SELECT count(*) FROM alerts WHERE status = 'open') AS open_alerts
            """
        ),
        p,
    ).mappings().one()
    return {
        "window_days": days,
        "earliest_detection_day": earliest,
        "totals": dict(totals),
        "observations_daily": observations,
        "incidents_daily": incidents,
        "persistence": persistence,
        "classifications": classifications,
        "facility_types": facility_types,
        "top_persistent_sources": top_sources,
    }


def grid(conn: Connection, days: int, cell: float) -> dict:
    """Detections binned into cell x cell degree squares (GeoJSON polygons)."""
    rows = conn.execute(
        text(
            """
            SELECT floor(latitude / :c) * :c AS s, floor(longitude / :c) * :c AS w,
                   count(*) AS detections, max(frp) AS max_frp,
                   count(DISTINCT cluster_id) AS clusters
              FROM thermal_observations
             WHERE acq_date > (now() AT TIME ZONE 'UTC')::date - :d
             GROUP BY 1, 2
            """
        ),
        {"c": cell, "d": days},
    ).mappings().all()
    features = []
    for r in rows:
        s, w = float(r["s"]), float(r["w"])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[w, s], [w + cell, s], [w + cell, s + cell], [w, s + cell], [w, s]]]},
            "properties": {"detections": r["detections"], "max_frp": r["max_frp"], "clusters": r["clusters"],
                           "south": s, "west": w, "cell_deg": cell},
        })
    return {"type": "FeatureCollection", "features": features}
