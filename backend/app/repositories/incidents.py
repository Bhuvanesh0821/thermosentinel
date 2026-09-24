"""Read/update queries for incidents, alerts and notifications."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.intelligence import CLASSIFICATION_LABELS
from app.config import PRIORITY_ORDER
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.repositories.filters import Where, feature_collection, point_feature

_INCIDENT_COLUMNS = """
    i.id, i.cluster_id, i.facility_id, i.title, i.classification, i.priority, i.risk_score, i.status,
    i.latitude, i.longitude, i.first_detected_at, i.last_detected_at, i.observation_count, i.max_frp,
    i.summary, i.acknowledged_at, i.closed_at, i.created_at, i.updated_at,
    f.name AS facility_name, f.facility_type, f.source_ref AS facility_source_ref,
    c.persistence_category, c.spatial_relationship, c.nearest_facility_distance_m, c.evidence_strength
"""

_PRIORITY_SORT = "CASE i.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"


def _decorate(row: dict) -> dict:
    row["reference"] = f"INC-{row['id']:06d}"
    row["classification_label"] = CLASSIFICATION_LABELS.get(row["classification"], row["classification"])
    if row.get("facility_type"):
        row["facility_type_label"] = FACILITY_TYPES.get(row["facility_type"], row["facility_type"])
    return row


def _where(
    statuses: list[str] | None,
    min_priority: str | None,
    classifications: list[str] | None = None,
    facility_types: list[str] | None = None,
    persistence: list[str] | None = None,
    hours: int | None = None,
    bbox=None,
    q: str | None = None,
) -> Where:
    w = Where()
    if statuses:
        w.add("i.status = ANY(CAST(:statuses AS text[]))", statuses=statuses)
    if min_priority:
        w.add("i.priority = ANY(CAST(:prios AS text[]))", prios=PRIORITY_ORDER[PRIORITY_ORDER.index(min_priority) :])
    if classifications:
        w.add("i.classification = ANY(CAST(:classes AS text[]))", classes=classifications)
    if facility_types:
        w.add("i.facility_id IN (SELECT id FROM industrial_facilities WHERE facility_type = ANY(CAST(:ftypes AS text[])))",
              ftypes=facility_types)
    if persistence:
        w.add("i.cluster_id IN (SELECT id FROM thermal_clusters WHERE persistence_category = ANY(CAST(:pers AS text[])))",
              pers=persistence)
    if hours:
        w.add("i.last_detected_at >= now() - make_interval(hours => :hours)", hours=hours)
    w.bbox("i.geom", bbox)
    if q:
        w.add("i.title ILIKE :q", q=f"%{q}%")
    return w


def incident_breakdown(conn: Connection, *, statuses: list[str] | None, min_priority: str | None, **filters) -> dict:
    """Counts by priority and by event class for the same filters as the incident list (for charts)."""
    w = _where(statuses, min_priority, **filters)
    by_priority = {r[0]: r[1] for r in conn.execute(text(f"SELECT i.priority, count(*) FROM incidents i {w.sql} GROUP BY 1"), w.params)}
    by_class = [
        {"classification": r[0], "label": CLASSIFICATION_LABELS.get(r[0], r[0]), "count": r[1]}
        for r in conn.execute(
            text(f"SELECT i.classification, count(*) FROM incidents i {w.sql} GROUP BY 1 ORDER BY 2 DESC"), w.params
        )
    ]
    return {"by_priority": by_priority, "by_classification": by_class}


def list_incidents(
    conn: Connection, *, statuses: list[str] | None, min_priority: str | None, limit: int, offset: int, **filters
) -> tuple[list[dict], int]:
    w = _where(statuses, min_priority, **filters)
    total = conn.execute(text(f"SELECT count(*) FROM incidents i {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(
            f"""
            SELECT {_INCIDENT_COLUMNS}
              FROM incidents i
              LEFT JOIN industrial_facilities f ON f.id = i.facility_id
              LEFT JOIN thermal_clusters c ON c.id = i.cluster_id
              {w.sql}
             ORDER BY {_PRIORITY_SORT}, i.risk_score DESC, i.last_detected_at DESC
             LIMIT :limit OFFSET :offset
            """
        ),
        {**w.params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [_decorate(dict(r)) for r in rows], int(total)


def incidents_geojson(conn: Connection, *, statuses: list[str] | None, min_priority: str | None, **filters) -> dict:
    rows, _ = list_incidents(conn, statuses=statuses, min_priority=min_priority, limit=5000, offset=0, **filters)
    return feature_collection(
        [
            point_feature(
                r["id"],
                r["latitude"],
                r["longitude"],
                {
                    k: r[k]
                    for k in (
                        "id", "reference", "title", "priority", "risk_score", "status", "classification",
                        "classification_label", "cluster_id", "facility_name", "last_detected_at",
                    )
                },
            )
            for r in rows
        ]
    )


def get_incident(conn: Connection, incident_id: int) -> dict | None:
    row = conn.execute(
        text(
            f"""
            SELECT {_INCIDENT_COLUMNS}, i.evidence
              FROM incidents i
              LEFT JOIN industrial_facilities f ON f.id = i.facility_id
              LEFT JOIN thermal_clusters c ON c.id = i.cluster_id
             WHERE i.id = :id
            """
        ),
        {"id": incident_id},
    ).mappings().one_or_none()
    if not row:
        return None
    incident = _decorate(dict(row))
    incident["alerts"] = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT id, alert_type, severity, title, description, status, rules, escalation_count, created_at, "
                "last_triggered_at, acknowledged_at, resolved_at, resolution FROM alerts "
                "WHERE incident_id = :id ORDER BY created_at DESC"
            ),
            {"id": incident_id},
        ).mappings()
    ]
    return incident


def acknowledge_incident(conn: Connection, incident_id: int) -> dict | None:
    row = conn.execute(
        text(
            "UPDATE incidents SET acknowledged_at = coalesce(acknowledged_at, now()) WHERE id = :id "
            "RETURNING id, acknowledged_at"
        ),
        {"id": incident_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


# ------------------------------------------------------------------------- alerts
_ALERT_COLUMNS = """
    a.id, a.incident_id, a.cluster_id, a.alert_type, a.severity, a.title, a.description, a.status, a.rules,
    a.escalation_count, a.source, a.latitude, a.longitude, a.created_at, a.updated_at, a.last_triggered_at,
    a.acknowledged_at, a.resolved_at, a.resolution,
    a.facility_id, f.name AS facility_name, f.facility_type, i.status AS incident_status, i.classification
"""


def _alert_where(statuses, min_severity, rule=None, q=None, hours=None) -> Where:
    w = Where()
    if statuses:
        w.add("a.status = ANY(CAST(:statuses AS text[]))", statuses=statuses)
    if min_severity:
        w.add("a.severity = ANY(CAST(:sev AS text[]))", sev=PRIORITY_ORDER[PRIORITY_ORDER.index(min_severity) :])
    if rule:
        w.add(":rule = ANY(a.rules)", rule=rule)
    if q:
        w.add("(a.title ILIKE :q OR a.description ILIKE :q)", q=f"%{q}%")
    if hours:
        w.add("a.last_triggered_at >= now() - make_interval(hours => :hours)", hours=hours)
    return w


def alert_breakdown(conn: Connection, *, statuses, min_severity, rule=None, q=None, hours=None) -> dict:
    """Counts by severity and by fired rule for the same filters as the alert list (for charts)."""
    w = _alert_where(statuses, min_severity, rule, q, hours)
    by_severity = {r[0]: r[1] for r in conn.execute(text(f"SELECT a.severity, count(*) FROM alerts a {w.sql} GROUP BY 1"), w.params)}
    by_rule = {
        r[0]: r[1]
        for r in conn.execute(
            text(f"SELECT r.rule, count(*) FROM alerts a CROSS JOIN LATERAL unnest(a.rules) AS r(rule) {w.sql} GROUP BY 1"),
            w.params,
        )
    }
    return {"by_severity": by_severity, "by_rule": by_rule}


def list_alerts(
    conn: Connection,
    *,
    statuses: list[str] | None,
    min_severity: str | None,
    limit: int,
    offset: int,
    rule: str | None = None,
    q: str | None = None,
    hours: int | None = None,
) -> tuple[list[dict], int]:
    w = _alert_where(statuses, min_severity, rule, q, hours)
    total = conn.execute(text(f"SELECT count(*) FROM alerts a {w.sql}"), w.params).scalar_one()
    rows = conn.execute(
        text(
            f"""
            SELECT {_ALERT_COLUMNS}
              FROM alerts a
              LEFT JOIN incidents i ON i.id = a.incident_id
              LEFT JOIN industrial_facilities f ON f.id = a.facility_id
              {w.sql}
             ORDER BY CASE a.status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                      CASE a.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                      a.last_triggered_at DESC
             LIMIT :limit OFFSET :offset
            """
        ),
        {**w.params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [_decorate_alert(dict(r)) for r in rows], int(total)


def _decorate_alert(row: dict) -> dict:
    row["alert_id"] = row["id"]
    row["location"] = (
        {"latitude": row["latitude"], "longitude": row["longitude"]} if row.get("latitude") is not None else None
    )
    row["facility"] = (
        {"id": row["facility_id"], "name": row.get("facility_name"), "type": row.get("facility_type"),
         "type_label": FACILITY_TYPES.get(row.get("facility_type") or "", row.get("facility_type"))}
        if row.get("facility_id")
        else None
    )
    return row


def get_alert(conn: Connection, alert_id: int) -> dict | None:
    row = conn.execute(
        text(
            f"""
            SELECT {_ALERT_COLUMNS}, a.evidence
              FROM alerts a
              LEFT JOIN incidents i ON i.id = a.incident_id
              LEFT JOIN industrial_facilities f ON f.id = a.facility_id
             WHERE a.id = :id
            """
        ),
        {"id": alert_id},
    ).mappings().one_or_none()
    if not row:
        return None
    alert = _decorate_alert(dict(row))
    alert["notifications"] = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT channel, recipient, event, status, sent_at, read_at, last_error FROM notifications "
                "WHERE alert_id = :id ORDER BY created_at"
            ),
            {"id": alert_id},
        ).mappings()
    ]
    return alert


def acknowledge_alert(conn: Connection, alert_id: int) -> dict | None:
    row = conn.execute(
        text(
            "UPDATE alerts SET status = CASE WHEN status = 'resolved' THEN status ELSE 'acknowledged' END, "
            "acknowledged_at = coalesce(acknowledged_at, now()) "
            "WHERE id = :id RETURNING id, status, acknowledged_at"
        ),
        {"id": alert_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def resolve_alert(conn: Connection, alert_id: int, note: str | None) -> dict | None:
    row = conn.execute(
        text(
            "UPDATE alerts SET status = 'resolved', resolved_at = coalesce(resolved_at, now()), "
            "resolution = coalesce(:note, 'Resolved by operator') "
            "WHERE id = :id RETURNING id, status, resolved_at, resolution"
        ),
        {"id": alert_id, "note": note},
    ).mappings().one_or_none()
    return dict(row) if row else None


# ------------------------------------------------------------------ notifications
def list_notifications(conn: Connection, *, unread_only: bool, limit: int) -> tuple[list[dict], int]:
    unread = conn.execute(
        text("SELECT count(*) FROM notifications WHERE channel = 'in_app' AND read_at IS NULL")
    ).scalar_one()
    rows = conn.execute(
        text(
            f"""
            SELECT n.id, n.alert_id, n.channel, n.event, n.title, n.body, n.status, n.created_at, n.read_at,
                   coalesce(n.severity, a.severity) AS severity, a.incident_id, a.status AS alert_status
              FROM notifications n LEFT JOIN alerts a ON a.id = n.alert_id
             WHERE n.channel = 'in_app' {"AND n.read_at IS NULL" if unread_only else ""}
             ORDER BY n.created_at DESC LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows], int(unread)


def mark_notifications_read(conn: Connection, ids: list[int] | None) -> int:
    if ids is None:
        result = conn.execute(
            text("UPDATE notifications SET read_at = now(), status = 'read' WHERE channel = 'in_app' AND read_at IS NULL")
        )
    else:
        result = conn.execute(
            text(
                "UPDATE notifications SET read_at = now(), status = 'read' "
                "WHERE id = ANY(CAST(:ids AS bigint[])) AND read_at IS NULL"
            ),
            {"ids": ids},
        )
    return result.rowcount or 0
