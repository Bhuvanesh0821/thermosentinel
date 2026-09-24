"""Spoken situation briefing.

Builds a plain-language briefing strictly from stored data; the frontend speaks it with the
browser's Web Speech API (no third-party voice service or key required in Stage 1). The
facts used are returned alongside the text so the briefing is auditable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.repositories.stats import summary


def _n(value: int, noun: str) -> str:
    return f"{value:,} {noun}{'' if value == 1 else 's'}"


def build_briefing(conn: Connection, hours: int = 24) -> dict:
    settings = get_settings()
    stats = summary(conn, hours)
    top = conn.execute(
        text(
            """
            SELECT id, title, priority, risk_score FROM incidents
             WHERE status IN ('active', 'monitoring')
             ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                      risk_score DESC
             LIMIT 3
            """
        )
    ).mappings().all()

    now = datetime.now(timezone.utc)
    det = stats["detections"]["total"]
    parts = [f"ThermoSentinel situation briefing for {settings.region_name}, generated at {now:%H:%M} UTC."]
    if stats["stored_detections"]["total"] == 0:
        parts.append("No satellite thermal detections have been ingested yet. Run the data pipeline to begin monitoring.")
    else:
        parts.append(
            f"In the last {hours} hours NASA FIRMS reported {_n(det, 'thermal detection')}"
            + (f", peaking at {stats['detections']['max_frp']:.0f} megawatts of fire radiative power." if det else ".")
        )
        c = stats["clusters"]
        parts.append(
            f"These form {_n(c['active'], 'active cluster')}, of which {c['industrial_associated']:,} "
            f"{'is' if c['industrial_associated'] == 1 else 'are'} associated with mapped industrial infrastructure "
            f"and {c['persistent']:,} show persistent activity."
        )
        inc = stats["incidents"]
        open_incidents = inc["active"] + inc["monitoring"]
        if open_incidents:
            parts.append(
                f"There {'is' if open_incidents == 1 else 'are'} {_n(open_incidents, 'open incident')}: "
                f"{inc['critical']} critical, {inc['high']} high, {inc['medium']} medium and {inc['low']} low priority."
            )
            for i, row in enumerate(top, start=1):
                parts.append(f"Priority {i}: {row['title']}, risk score {row['risk_score']:.0f} out of 100.")
        else:
            parts.append("There are no open incidents.")
        if stats["alerts"]["open"]:
            parts.append(f"{_n(stats['alerts']['open'], 'alert')} awaiting acknowledgement.")
    parts.append("Classifications are inferred from satellite and open geospatial data and require verification.")
    return {
        "text": " ".join(parts),
        "generated_at": now,
        "facts": {
            "window_hours": hours,
            "detections": det,
            "clusters": stats["clusters"],
            "incidents": stats["incidents"],
            "open_alerts": stats["alerts"]["open"],
            "top_incidents": [dict(r) for r in top],
        },
    }
