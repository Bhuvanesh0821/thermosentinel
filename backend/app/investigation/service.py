"""Incident investigation workspace: one evidence trail from raw detections to alerts.

Everything returned is read from stored data; the timeline is reconstructed from recorded
timestamps (detections, incident, alert and notification rows), never inferred.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.classifier import CLASSES
from app.geo.boundary import get_monitoring_area
from app.ingestion.facilities.classify import FACILITY_TYPES, THERMAL_RELEVANCE
from app.ingestion.landcover.worldcover import WORLDCOVER_CLASSES
from app.repositories.clusters import get_cluster
from app.repositories.incidents import get_incident


def investigation(conn: Connection, incident_id: int) -> dict | None:
    incident = get_incident(conn, incident_id)
    if not incident:
        return None
    cluster = get_cluster(conn, incident["cluster_id"], observation_limit=5000) or {}

    facility = None
    if incident.get("facility_id"):
        row = conn.execute(
            text(
                """
                SELECT id, name, facility_type, facility_subtype, operator, website, source_ref, latitude, longitude,
                       footprint_area_m2, source_timestamp, tags, ST_AsGeoJSON(footprint, 6)::json AS footprint
                  FROM industrial_facilities WHERE id = :id
                """
            ),
            {"id": incident["facility_id"]},
        ).mappings().one_or_none()
        if row:
            facility = dict(row)
            facility["type_label"] = FACILITY_TYPES.get(facility["facility_type"], facility["facility_type"])
            facility["thermal_relevance"] = THERMAL_RELEVANCE.get(facility["facility_type"], None)
            facility["source_url"] = f"https://www.openstreetmap.org/{facility['source_ref']}"

    # Per-day and per-satellite summaries of the member detections.
    daily = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT acq_date AS day, count(*) AS detections, max(frp) AS max_frp, avg(frp) AS mean_frp,
                       count(*) FILTER (WHERE daynight = 'N') AS night,
                       array_agg(DISTINCT satellite_name) AS satellites
                  FROM thermal_observations WHERE cluster_id = :cid
                 GROUP BY acq_date ORDER BY acq_date
                """
            ),
            {"cid": incident["cluster_id"]},
        ).mappings()
    ]
    satellites = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT satellite_name, instrument, product, count(*) AS detections, max(frp) AS max_frp,
                       min(acquired_at) AS first_seen, max(acquired_at) AS last_seen,
                       count(*) FILTER (WHERE confidence_level = 'high') AS high_confidence
                  FROM thermal_observations WHERE cluster_id = :cid
                 GROUP BY satellite_name, instrument, product ORDER BY detections DESC
                """
            ),
            {"cid": incident["cluster_id"]},
        ).mappings()
    ]
    runs = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT r.id, r.job, r.status, r.started_at, r.params ->> 'mode' AS mode, count(o.id) AS detections
                  FROM thermal_observations o JOIN ingestion_runs r ON r.id = o.ingestion_run_id
                 WHERE o.cluster_id = :cid GROUP BY r.id ORDER BY r.started_at
                """
            ),
            {"cid": incident["cluster_id"]},
        ).mappings()
    ]
    notifications = [
        dict(r)
        for r in conn.execute(
            text(
                """
                SELECT n.alert_id, n.channel, n.event, n.status, n.created_at, n.read_at
                  FROM notifications n JOIN alerts a ON a.id = n.alert_id
                 WHERE a.incident_id = :iid ORDER BY n.created_at
                """
            ),
            {"iid": incident_id},
        ).mappings()
    ]

    timeline = _timeline(incident, cluster, daily, notifications)
    intel = cluster.get("intelligence") or incident.get("evidence") or {}
    area = get_monitoring_area()
    return {
        "incident": {k: v for k, v in incident.items() if k != "evidence"},
        "classification": {
            "key": incident["classification"],
            "label": CLASSES.get(incident["classification"], incident["classification"]),
            "evidence_strength": cluster.get("evidence_strength"),
            "rationale": intel.get("classification_rationale", []),
            "alternatives_rejected": intel.get("alternatives_rejected", []),
            "classifier": intel.get("classifier"),
        },
        "intelligence": {
            "intelligence_score": intel.get("intelligence_score", cluster.get("risk_score")),
            "risk_level": intel.get("risk_level", cluster.get("priority")),
            "factors": intel.get("factors", []),
            "evidence": intel.get("evidence", []),
            "hypotheses": intel.get("hypotheses", []),
            "caveats": intel.get("caveats", []),
            "engine_version": intel.get("engine_version"),
            "analyzed_at": cluster.get("analyzed_at"),
        },
        "cluster": {k: v for k, v in cluster.items() if k not in ("observations", "intelligence")},
        "observations": cluster.get("observations", []),
        "daily": daily,
        "satellites": satellites,
        "facility": facility,
        "nearby_facilities": cluster.get("nearby_facilities", []),
        "land_cover": {
            "status": cluster.get("land_cover_status"),
            "dominant": cluster.get("land_cover_class"),
            "fractions": cluster.get("land_cover_fractions") or {},
            "legend": {str(k): {"name": n, "color": c} for k, (n, c) in WORLDCOVER_CLASSES.items()},
            "dataset": cluster.get("land_cover_dataset"),
            "tile": cluster.get("land_cover_tile"),
            "radius_m": cluster.get("land_cover_radius_m"),
        },
        "alerts": incident.get("alerts", []),
        "timeline": timeline,
        "provenance": {
            "thermal": {
                "source": "NASA FIRMS (LANCE) active fire / thermal anomalies",
                "products": sorted({s["product"] for s in satellites}),
                "ingestion_runs": runs,
            },
            "facility": (
                {"source": "OpenStreetMap contributors (ODbL) via Overpass API", "element": facility["source_ref"],
                 "url": facility["source_url"], "snapshot": facility["source_timestamp"]}
                if facility
                else None
            ),
            "land_cover": (
                {"source": f"ESA WorldCover 10 m {cluster.get('land_cover_dataset')} (CC BY 4.0)", "tile": cluster.get("land_cover_tile"),
                 "sampled_at": cluster.get("land_cover_sampled_at")}
                if cluster.get("land_cover_status")
                else None
            ),
            "boundary": area.properties.get("monitoring_area", {}).get("source"),
            "analysis": {"engine": intel.get("engine_version"), "classifier": intel.get("classifier"), "analyzed_at": cluster.get("analyzed_at")},
        },
    }


def _timeline(incident: dict, cluster: dict, daily: list[dict], notifications: list[dict]) -> list[dict]:
    ev: list[dict] = []
    if cluster.get("start_time"):
        ev.append({"at": cluster["start_time"], "kind": "detection", "title": "First satellite detection of this event",
                   "detail": f"Cluster #{cluster.get('id')} starts"})
    for d in daily:
        ev.append({
            "at": f"{d['day']}T23:59:59+00:00", "kind": "daily", "day": d["day"],
            "title": f"{d['detections']} detection{'s' if d['detections'] != 1 else ''} on {d['day']}",
            "detail": f"Max FRP {d['max_frp'] or 0:.1f} MW · {d['night']} at night · {', '.join(s for s in d['satellites'] if s)}",
        })
    ev.append({"at": incident["created_at"], "kind": "incident", "title": f"Incident {incident['reference']} opened",
               "detail": f"{incident['classification_label']} · priority {incident['priority']}"})
    for n in notifications:
        if n["channel"] != "in_app":
            continue
        is_esc = str(n["event"]).startswith("escalated")
        ev.append({"at": n["created_at"], "kind": "alert", "title": ("Alert escalated" if is_esc else "Alert raised") + f" (#{n['alert_id']})",
                   "detail": n["event"]})
    for a in incident.get("alerts", []):
        if a.get("acknowledged_at"):
            ev.append({"at": a["acknowledged_at"], "kind": "operator", "title": f"Alert #{a['id']} acknowledged", "detail": ""})
        if a.get("resolved_at"):
            ev.append({"at": a["resolved_at"], "kind": "resolution", "title": f"Alert #{a['id']} resolved", "detail": a.get("resolution") or ""})
    if incident.get("acknowledged_at"):
        ev.append({"at": incident["acknowledged_at"], "kind": "operator", "title": "Incident acknowledged", "detail": ""})
    if incident.get("closed_at"):
        ev.append({"at": incident["closed_at"], "kind": "resolution", "title": "Incident closed", "detail": "No detections for 72 hours"})
    if cluster.get("end_time"):
        ev.append({"at": cluster["end_time"], "kind": "detection", "title": "Latest satellite detection", "detail": ""})
    for e in ev:  # one comparable representation: UTC ISO-8601
        if isinstance(e["at"], datetime):
            e["at"] = e["at"].astimezone(timezone.utc).isoformat()
    return sorted(ev, key=lambda e: e["at"])
