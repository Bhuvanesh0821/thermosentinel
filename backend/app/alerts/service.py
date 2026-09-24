"""Incident lifecycle and the rule-based alert engine.

Incidents: an active cluster whose classification is an industrial/persistent class and whose
intelligence score >= INCIDENT_MIN_SCORE. Status follows the latest detection: active (<24 h),
monitoring (<72 h), closed.

Alerts (app/alerts/rules.py): for each open incident the configured rules are evaluated on
real, stored evidence. One alert exists per underlying event (a partial unique index enforces
at most one unresolved alert per incident): rules that fire later update it, and a higher
severity escalates it (notifying again). Alerts resolve automatically when their incident closes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.alerts.rules import RANK, RULES, RecentActivity, evaluate, severity_for
from app.analytics.classifier import CLASSES, INCIDENT_CLASSES
from app.config import Settings, get_settings
from app.core.events import bus
from app.db.engine import transaction
from app.ingestion.facilities.classify import FACILITY_TYPES, THERMAL_RELEVANCE
from app.notifications.service import create_in_app, dispatch_external

log = logging.getLogger(__name__)


def _facility_display(name: str | None, ftype: str | None) -> str:
    return name or f"unnamed {FACILITY_TYPES.get(ftype or '', 'industrial facility').lower()}"


def _title(row: dict) -> str:
    cls = row["classification"]
    fac = _facility_display(row["facility_name"], row["facility_type"]) if row["facility_id"] else None
    where = f"{row['center_latitude']:.3f}, {row['center_longitude']:.3f}"
    templates = {
        "gas_flare_like": f"Gas-flare-like activity at {fac}" if fac else f"Gas-flare-like activity offshore at {where}",
        "mining_associated": f"Mining-associated thermal activity at {fac}",
        "persistent_industrial_source": f"Persistent industrial thermal source at {fac}",
        "industrial_associated_event": f"Industrial-associated thermal event near {fac}",
        "persistent_unattributed_source": f"Persistent thermal source at {where} (no mapped facility)",
    }
    return templates.get(cls) or f"{CLASSES.get(cls, cls)} at {where}"


def refresh_incident_status(conn) -> int:
    return (
        conn.execute(
            text(
                """
                UPDATE incidents i
                   SET status = s.new_status,
                       closed_at = CASE WHEN s.new_status = 'closed' THEN coalesce(i.closed_at, now()) ELSE NULL END
                  FROM (
                        SELECT i2.id,
                               CASE WHEN i2.last_detected_at >= now() - interval '24 hours' THEN 'active'
                                    WHEN i2.last_detected_at >= now() - interval '72 hours' THEN 'monitoring'
                                    ELSE 'closed' END AS new_status
                          FROM incidents i2 WHERE i2.status <> 'closed'
                       ) s
                 WHERE i.id = s.id AND i.status <> s.new_status
                """
            )
        ).rowcount
        or 0
    )


def resolve_closed_incident_alerts(conn) -> list[dict]:
    rows = conn.execute(
        text(
            """
            UPDATE alerts a SET status = 'resolved', resolved_at = now(),
                   resolution = 'Auto-resolved: no detections at this location for 72 hours (incident closed)',
                   resolved_by = 'system'
              FROM incidents i
             WHERE a.incident_id = i.id AND i.status = 'closed' AND a.status <> 'resolved'
            RETURNING a.id, a.incident_id, a.severity, a.title
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def close_disqualified_incidents(conn, settings: Settings) -> list[dict]:
    """Close open incidents whose event no longer qualifies after re-analysis (reclassified into a
    non-incident class, score below INCIDENT_MIN_SCORE, or cluster merged/inactive). The incident
    keeps its latest class and score, and its open alert is resolved with the reason."""
    rows = conn.execute(
        text(
            """
            WITH d AS (
                SELECT i.id, c.classification, c.priority, c.risk_score
                  FROM incidents i
                  LEFT JOIN thermal_clusters c ON c.id = i.cluster_id
                 WHERE i.status <> 'closed'
                   AND (c.id IS NULL OR c.status <> 'active' OR c.classification IS NULL
                        OR NOT (c.classification = ANY(CAST(:classes AS text[])))
                        OR c.risk_score < :min_score)
            ), upd AS (
                UPDATE incidents i
                   SET status = 'closed', closed_at = now(),
                       classification = coalesce(d.classification, i.classification),
                       priority = coalesce(d.priority, i.priority),
                       risk_score = coalesce(d.risk_score, i.risk_score)
                  FROM d
                 WHERE i.id = d.id
             RETURNING i.id, i.classification, i.risk_score
            )
            UPDATE alerts a
               SET status = 'resolved', resolved_at = now(), resolved_by = 'system',
                   resolution = 'Auto-resolved: after re-analysis the event no longer meets the incident criteria '
                                || '(class ' || upd.classification || ', intelligence score '
                                || round(upd.risk_score::numeric) || ')'
              FROM upd
             WHERE a.incident_id = upd.id AND a.status <> 'resolved'
         RETURNING a.id, a.incident_id, a.severity, a.title
            """
        ),
        {"classes": sorted(INCIDENT_CLASSES), "min_score": settings.incident_min_score},
    ).mappings().all()
    return [dict(r) for r in rows]


def _upsert_incidents(conn, candidates, settings: Settings) -> list[dict]:
    out = []
    for c in candidates:
        intel = c["intelligence"] or {}
        title = _title(c)
        row = conn.execute(
            text(
                """
                INSERT INTO incidents (
                    cluster_id, facility_id, title, classification, priority, risk_score, status,
                    latitude, longitude, geom, first_detected_at, last_detected_at,
                    observation_count, max_frp, summary, evidence
                ) VALUES (
                    :cluster_id, :facility_id, :title, :classification, :priority, :risk_score,
                    CASE WHEN CAST(:end_time AS timestamptz) >= now() - interval '24 hours' THEN 'active'
                         WHEN CAST(:end_time AS timestamptz) >= now() - interval '72 hours' THEN 'monitoring'
                         ELSE 'closed' END,
                    :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :start_time, :end_time, :n, :max_frp, :summary, CAST(:evidence AS jsonb)
                )
                ON CONFLICT (cluster_id) DO UPDATE SET
                    facility_id = EXCLUDED.facility_id, title = EXCLUDED.title,
                    classification = EXCLUDED.classification, priority = EXCLUDED.priority,
                    risk_score = EXCLUDED.risk_score, status = EXCLUDED.status,
                    latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, geom = EXCLUDED.geom,
                    first_detected_at = LEAST(incidents.first_detected_at, EXCLUDED.first_detected_at),
                    last_detected_at = EXCLUDED.last_detected_at,
                    observation_count = EXCLUDED.observation_count, max_frp = EXCLUDED.max_frp,
                    summary = EXCLUDED.summary, evidence = EXCLUDED.evidence,
                    closed_at = CASE WHEN EXCLUDED.status = 'closed' THEN coalesce(incidents.closed_at, now()) ELSE NULL END
                RETURNING id, status, (xmax = 0) AS inserted
                """
            ),
            {
                "cluster_id": c["cluster_id"], "facility_id": c["facility_id"], "title": title,
                "classification": c["classification"], "priority": c["priority"], "risk_score": c["risk_score"],
                "lat": c["center_latitude"], "lon": c["center_longitude"], "start_time": c["start_time"],
                "end_time": c["end_time"], "n": c["observation_count"], "max_frp": c["max_frp"],
                "summary": " ".join(intel.get("evidence", [])[:2]), "evidence": json.dumps(intel),
            },
        ).mappings().one()
        out.append({**c, "incident_id": row["id"], "incident_status": row["status"], "inserted": row["inserted"], "title": title})
    return out


def _recent_activity(conn, cluster_ids: list[int], settings: Settings) -> dict[int, RecentActivity]:
    if not cluster_ids:
        return {}
    recent = {
        r["cluster_id"]: dict(r)
        for r in conn.execute(
            text(
                """
                SELECT o.cluster_id,
                       count(*) FILTER (WHERE o.acquired_at >= now() - interval '24 hours') AS n24,
                       max(o.frp) FILTER (WHERE o.acquired_at >= now() - interval '24 hours') AS frp24,
                       count(*) FILTER (WHERE o.acquired_at >= now() - interval '24 hours'
                                          AND o.confidence_level = 'high' AND o.frp >= :minfrp) AS hc24
                  FROM thermal_observations o
                 WHERE o.cluster_id = ANY(CAST(:ids AS bigint[]))
                 GROUP BY o.cluster_id
                """
            ),
            {"ids": cluster_ids, "minfrp": settings.alert_rule_high_confidence_min_frp},
        ).mappings()
    }
    prior = {
        r["id"]: dict(r)
        for r in conn.execute(
            text(
                """
                SELECT c.id,
                       count(o.id) AS prior_n,
                       count(DISTINCT o.acq_date) AS prior_days_seen
                  FROM thermal_clusters c
                  JOIN thermal_observations o
                    ON ST_DWithin(o.geom, c.geom, :radius)
                   AND o.acquired_at >= now() - make_interval(days => :lookback)
                   AND o.acquired_at < now() - interval '24 hours'
                 WHERE c.id = ANY(CAST(:ids AS bigint[]))
                 GROUP BY c.id
                """
            ),
            {"ids": cluster_ids, "radius": settings.persistence_radius_m, "lookback": settings.persistence_lookback_days},
        ).mappings()
    }
    coverage_prior = conn.execute(
        text(
            "SELECT count(DISTINCT acq_date) FROM thermal_observations "
            "WHERE acquired_at >= now() - make_interval(days => :d) AND acquired_at < now() - interval '24 hours'"
        ),
        {"d": settings.persistence_lookback_days},
    ).scalar_one()
    out = {}
    for cid in cluster_ids:
        r = recent.get(cid, {})
        p = prior.get(cid, {})
        out[cid] = RecentActivity(
            detections_24h=int(r.get("n24") or 0),
            max_frp_24h=r.get("frp24"),
            high_confidence_24h=int(r.get("hc24") or 0),
            prior_detections=int(p.get("prior_n") or 0),
            prior_days=int(coverage_prior or 0),
        )
    return out


def _alert_evidence(c: dict, hits, severity: str) -> dict:
    intel = c["intelligence"] or {}
    return {
        "rules": [h.as_dict() for h in hits],
        "intelligence_score": c["risk_score"],
        "risk_level": c["priority"],
        "alert_severity": severity,
        "classification": c["classification"],
        "classification_label": CLASSES.get(c["classification"], c["classification"]),
        "evidence": intel.get("evidence", []),
        "caveats": intel.get("caveats", []),
        "cluster_id": c["cluster_id"],
        "facility": {"id": c["facility_id"], "name": c["facility_name"], "type": c["facility_type"]} if c["facility_id"] else None,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_incidents_and_alerts(cluster_ids: list[int], settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    min_rank = RANK[settings.alert_min_priority]
    stats = {"candidates": 0, "new_incidents": 0, "updated_incidents": 0, "alerts_created": 0, "alerts_escalated": 0,
             "alerts_updated": 0, "alerts_resolved": 0, "status_changes": 0}
    notify: list[dict] = []
    resolved: list[dict] = []

    with transaction() as conn:
        candidates = [
            dict(r)
            for r in conn.execute(
                text(
                    """
                    SELECT c.id AS cluster_id, c.classification, c.priority, c.risk_score, c.center_latitude,
                           c.center_longitude, c.start_time, c.end_time, c.observation_count, c.max_frp,
                           c.intelligence, c.spatial_relationship, c.nearest_facility_distance_m,
                           c.persistence_category, c.persistence_detection_days, c.persistence_coverage_days,
                           CASE WHEN c.industrial_association THEN c.nearest_facility_id END AS facility_id,
                           f.name AS facility_name, f.facility_type
                      FROM thermal_clusters c
                      LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id AND c.industrial_association
                     WHERE c.id = ANY(CAST(:ids AS bigint[]))
                       AND c.status = 'active'
                       AND c.classification = ANY(CAST(:classes AS text[]))
                       AND c.risk_score >= :min_score
                    """
                ),
                {"ids": cluster_ids, "classes": sorted(INCIDENT_CLASSES), "min_score": settings.incident_min_score},
            ).mappings()
        ]
        stats["candidates"] = len(candidates)
        incidents = _upsert_incidents(conn, candidates, settings)
        stats["new_incidents"] = sum(1 for i in incidents if i["inserted"])
        stats["updated_incidents"] = len(incidents) - stats["new_incidents"]

        open_incidents = [i for i in incidents if i["incident_status"] != "closed"]
        activity = _recent_activity(conn, [i["cluster_id"] for i in open_incidents], settings)
        existing = {
            r["incident_id"]: dict(r)
            for r in conn.execute(
                text(
                    "SELECT id, incident_id, severity, status, rules FROM alerts "
                    "WHERE status <> 'resolved' AND incident_id = ANY(CAST(:ids AS bigint[]))"
                ),
                {"ids": [i["incident_id"] for i in open_incidents]},
            ).mappings()
        }

        # An operator's resolution is respected: no new alert for that incident for 7 days unless
        # the evidence escalates above the severity they resolved.
        operator_resolved = {
            r["incident_id"]: r["severity"]
            for r in conn.execute(
                text(
                    "SELECT DISTINCT ON (incident_id) incident_id, severity FROM alerts "
                    "WHERE resolved_by = 'operator' AND resolved_at >= now() - interval '7 days' "
                    "AND incident_id = ANY(CAST(:ids AS bigint[])) ORDER BY incident_id, resolved_at DESC"
                ),
                {"ids": [i["incident_id"] for i in open_incidents]},
            ).mappings()
        }
        stats["alerts_suppressed"] = 0

        for inc in open_incidents:
            inc["facility_relevance"] = THERMAL_RELEVANCE.get(inc["facility_type"] or "", 0.0)
            inc["facility_distance_m"] = inc["nearest_facility_distance_m"]
            hits = evaluate(inc, activity[inc["cluster_id"]], settings)
            if not hits:
                continue
            severity = severity_for(inc["priority"], hits, inc["spatial_relationship"] in ("inside_footprint", "adjacent"))
            if RANK[severity] < min_rank:
                continue
            rule_keys = [h.key for h in hits]
            description = (
                f"{CLASSES.get(inc['classification'], inc['classification'])}; intelligence score "
                f"{inc['risk_score']:.0f}/100. " + " ".join(h.detail + "." for h in hits)
            )
            evidence = json.dumps(_alert_evidence(inc, hits, severity), default=str)
            prev = existing.get(inc["incident_id"])
            if prev is None and inc["incident_id"] in operator_resolved and RANK[severity] <= RANK[operator_resolved[inc["incident_id"]]]:
                stats["alerts_suppressed"] += 1
                continue
            if prev is None:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO alerts (incident_id, cluster_id, facility_id, alert_type, severity, title, description,
                                            status, evidence, latitude, longitude, geom, rules, last_triggered_at)
                        VALUES (:iid, :cid, :fid, 'event', :sev, :title, :descr, 'open', CAST(:ev AS jsonb),
                                :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                                CAST(:rules AS text[]), now())
                        ON CONFLICT (incident_id) WHERE status <> 'resolved' DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "iid": inc["incident_id"], "cid": inc["cluster_id"], "fid": inc["facility_id"], "sev": severity,
                        "title": inc["title"], "descr": description, "ev": evidence, "lat": inc["center_latitude"],
                        "lon": inc["center_longitude"], "rules": rule_keys,
                    },
                ).first()
                if row:
                    stats["alerts_created"] += 1
                    notify.append({"id": row[0], "incident_id": inc["incident_id"], "title": inc["title"], "description": description,
                                   "severity": severity, "event": "created", "rules": rule_keys,
                                   "latitude": inc["center_latitude"], "longitude": inc["center_longitude"]})
                continue

            escalated = RANK[severity] > RANK[prev["severity"]]
            merged_rules = sorted(set(prev["rules"] or []) | set(rule_keys))
            conn.execute(
                text(
                    """
                    UPDATE alerts SET title = :title, description = :descr, evidence = CAST(:ev AS jsonb),
                           rules = CAST(:rules AS text[]), last_triggered_at = now(), facility_id = :fid,
                           severity = CASE WHEN :esc THEN :sev ELSE severity END,
                           escalation_count = escalation_count + CASE WHEN :esc THEN 1 ELSE 0 END,
                           status = CASE WHEN :esc THEN 'open' ELSE status END
                     WHERE id = :id
                    """
                ),
                {"id": prev["id"], "title": inc["title"], "descr": description, "ev": evidence, "rules": merged_rules,
                 "fid": inc["facility_id"], "sev": severity, "esc": escalated},
            )
            if escalated:
                stats["alerts_escalated"] += 1
                notify.append({"id": prev["id"], "incident_id": inc["incident_id"], "title": f"Escalated to {severity}: {inc['title']}",
                               "description": description, "severity": severity, "event": f"escalated:{severity}",
                               "rules": merged_rules, "latitude": inc["center_latitude"], "longitude": inc["center_longitude"]})
            else:
                stats["alerts_updated"] += 1

        disqualified = close_disqualified_incidents(conn, settings)
        stats["status_changes"] = refresh_incident_status(conn)
        resolved = disqualified + resolve_closed_incident_alerts(conn)
        stats["alerts_resolved"] = len(resolved)
        create_in_app(conn, notify)

    if notify:
        dispatch_external(notify, settings)
        for a in notify:
            bus.publish(
                "alert.created" if a["event"] == "created" else "alert.escalated",
                {k: a[k] for k in ("id", "incident_id", "title", "severity", "latitude", "longitude")} | {"alert_id": a["id"]},
            )
    for a in resolved:
        bus.publish("alert.resolved", {"alert_id": a["id"], "incident_id": a["incident_id"], "title": a["title"]})
    return stats


def rules_config(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    off = s.disabled_alert_rules
    return {
        "min_alert_severity": s.alert_min_priority,
        "incident_min_score": s.incident_min_score,
        "rules": [
            {"key": "high_intensity", "label": RULES["high_intensity"], "enabled": "high_intensity" not in off,
             "condition": f"max FRP in last 24 h >= {s.alert_rule_high_frp_mw:g} MW", "raises_severity": True},
            {"key": "repeated_observations", "label": RULES["repeated_observations"], "enabled": "repeated_observations" not in off,
             "condition": f">= {s.alert_rule_repeat_min_24h} detections in last 24 h", "raises_severity": False},
            {"key": "persistent_activity", "label": RULES["persistent_activity"], "enabled": "persistent_activity" not in off,
             "condition": "location classified persistent", "raises_severity": False},
            {"key": "industrial_proximity", "label": RULES["industrial_proximity"], "enabled": "industrial_proximity" not in off,
             "condition": "inside or <= 1 km of a thermally relevant facility (relevance >= 0.6)", "raises_severity": False},
            {"key": "unusual_activity", "label": RULES["unusual_activity"], "enabled": "unusual_activity" not in off,
             "condition": f"last-24 h detections >= {s.alert_rule_spike_factor:g} x the location's daily baseline and >= {s.alert_rule_spike_min_24h}",
             "raises_severity": True},
            {"key": "high_confidence", "label": RULES["high_confidence"], "enabled": "high_confidence" not in off,
             "condition": f"high-confidence detection with FRP >= {s.alert_rule_high_confidence_min_frp:g} MW in last 24 h",
             "raises_severity": False},
        ],
        "deduplication": "One alert per incident while unresolved; later rule hits update it, higher severity escalates it.",
        "resolution": "Alerts auto-resolve when their incident closes (no detections for 72 h).",
    }
