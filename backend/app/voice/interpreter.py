"""Voice / command interpreter.

Translates a spoken or typed request into ONE safe, whitelisted application action:
  navigate  - open a page (optionally with filters)
  focus     - fly the map to a real location (event, facility or geocoded place)
  answer    - a factual answer computed from stored data
Nothing else can be triggered (no writes, no deletes, no arbitrary queries). Unsupported
requests return `supported: false` with suggestions - the UI never pretends they ran.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.classifier import CLASSES, INCIDENT_CLASSES
from app.ingestion.facilities.classify import FACILITY_TYPES

INDUSTRIAL_CLASSES = sorted(INCIDENT_CLASSES - {"persistent_unattributed_source"})

FACILITY_SYNONYMS: list[tuple[str, str]] = [
    (r"power (?:plant|station)s?|thermal (?:power )?(?:plant|station)s?|power", "thermal_power_plant"),
    (r"petro ?chemical(?:s| plants?| complex(?:es)?)?", "petrochemical"),
    (r"refiner(?:y|ies)", "refinery"),
    (r"steel(?: plants?| mills?| works)?", "steel_plant"),
    (r"(?:gas )?flares?(?: stacks?)?", "gas_flare"),
    (r"lng(?: terminals?)?", "lng_terminal"),
    (r"oil (?:and|&) gas(?: facilities| sites?)?|oil ?fields?", "oil_gas_facility"),
    (r"smelters?|foundr(?:y|ies)|alumin(?:i)?um", "metal_smelter"),
    (r"cement(?: plants?| works)?", "cement_plant"),
    (r"(?:brick )?kilns?|brick", "brick_kiln"),
    (r"(?:coal )?mines?|mining(?: areas?)?|quarr(?:y|ies)", "mining"),
    (r"chemical(?: plants?)?|fertili[sz]er(?: plants?)?", "chemical_plant"),
]
PAGES = {
    "dashboard": "/dashboard", "map": "/dashboard", "home": "/dashboard", "monitor": "/dashboard",
    "incidents": "/incidents", "alerts": "/alerts", "alert centre": "/alerts", "alert center": "/alerts",
    "facilities": "/facilities", "thermal sources": "/thermal-sources", "persistent sources": "/thermal-sources",
    "sources": "/thermal-sources", "analytics": "/analytics", "charts": "/analytics", "settings": "/settings",
    "system health": "/settings", "health": "/settings",
}
PRIORITY_WORDS = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "urgent": "high", "severe": "high"}

EXAMPLES = [
    "Show active thermal anomalies",
    "Show high priority industrial incidents",
    "How many persistent thermal sources are active?",
    "Show incidents near power plants",
    "Open the latest alert",
    "Zoom to the latest industrial thermal event",
    "Zoom to Jamnagar",
    "How many open alerts are there?",
    "Give me a briefing",
    "Open analytics",
]


@dataclass
class Interpretation:
    supported: bool
    intent: str | None
    interpreted_as: str
    action: dict | None = None
    answer: str | None = None
    data: dict | None = None
    suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def normalise(raw: str) -> str:
    s = raw.lower().strip()
    s = re.sub(r"[^\w\s&'-]", " ", s)
    s = re.sub(r"\b(please|could you|can you|would you|kindly|hey|ok|okay|thermosentinel)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _facility_type(s: str) -> str | None:
    for pattern, ftype in FACILITY_SYNONYMS:
        if re.search(rf"\b(?:{pattern})\b", s):
            return ftype
    return None


def _priority(s: str) -> str | None:
    for word, p in PRIORITY_WORDS.items():
        if re.search(rf"\b{word}\b", s):
            return p
    return None


def _unsupported(raw: str) -> Interpretation:
    return Interpretation(
        supported=False,
        intent=None,
        interpreted_as=f'Not a supported command: "{raw.strip()}"',
        answer="I can't do that yet. Try one of the supported commands.",
        suggestions=EXAMPLES,
    )


def interpret(raw: str, conn: Connection) -> Interpretation:
    s = normalise(raw)
    if not s:
        return _unsupported(raw)

    # ---------------------------------------------------------------- help
    # Matched on the raw text too: normalise() strips "can you" as politeness.
    if re.search(r"\b(help|commands?|what can i say)\b", s) or re.search(r"\bwhat can you do\b", raw.lower()):
        return Interpretation(True, "help", "List supported commands", answer="Here is what I can do.", suggestions=EXAMPLES)

    # ------------------------------------------------------------- counts
    if re.search(r"\bhow many\b|\bcount\b|\bnumber of\b", s):
        if "persistent" in s or "thermal source" in s:
            row = conn.execute(
                text(
                    """
                    SELECT count(*) AS total,
                           count(*) FILTER (WHERE industrial_association) AS industrial
                      FROM thermal_clusters
                     WHERE status = 'active' AND persistence_category = 'persistent'
                    """
                )
            ).mappings().one()
            return Interpretation(
                True, "count_persistent_sources", "Count active persistent thermal sources",
                answer=(f"There {'is' if row['total'] == 1 else 'are'} {row['total']} active persistent thermal "
                        f"source{'s' if row['total'] != 1 else ''}; {row['industrial']} associated with mapped industrial facilities."),
                data=dict(row), action={"type": "navigate", "path": "/thermal-sources?persistence=persistent"},
            )
        if "alert" in s:
            n = conn.execute(text("SELECT count(*) FROM alerts WHERE status = 'open'")).scalar_one()
            return Interpretation(True, "count_alerts", "Count open alerts",
                                  answer=f"There {'is' if n == 1 else 'are'} {n} open alert{'s' if n != 1 else ''}.", data={"open": n})
        if "incident" in s:
            prio = _priority(s)
            q = "SELECT count(*) FROM incidents WHERE status IN ('active','monitoring')"
            params: dict = {}
            if prio:
                q += " AND priority = :p"
                params["p"] = prio
            n = conn.execute(text(q), params).scalar_one()
            label = f"{prio}-priority " if prio else ""
            return Interpretation(True, "count_incidents", f"Count open {label}incidents",
                                  answer=f"There {'is' if n == 1 else 'are'} {n} open {label}incident{'s' if n != 1 else ''}.", data={"open": n})
        if re.search(r"\b(anomal|detection|hotspot|fire)", s):
            n = conn.execute(text("SELECT count(*) FROM thermal_observations WHERE acquired_at >= now() - interval '24 hours'")).scalar_one()
            return Interpretation(True, "count_detections", "Count thermal detections in the last 24 hours",
                                  answer=f"NASA FIRMS recorded {n} thermal detection{'s' if n != 1 else ''} in India in the last 24 hours.", data={"detections_24h": n})
        if "facilit" in s:
            n = conn.execute(text("SELECT count(*) FROM industrial_facilities WHERE is_active")).scalar_one()
            return Interpretation(True, "count_facilities", "Count monitored facilities", answer=f"{n} industrial facilities are monitored.", data={"facilities": n})

    # -------------------------------------------------------------- latest alert
    if re.search(r"\b(open|show|read)\b.*\b(latest|last|newest|most recent|recent)\b.*\balert\b", s) or s in ("latest alert", "last alert"):
        row = conn.execute(
            text("SELECT id, incident_id, title, severity FROM alerts ORDER BY last_triggered_at DESC LIMIT 1")
        ).mappings().one_or_none()
        if not row:
            return Interpretation(True, "open_latest_alert", "Open the latest alert", answer="There are no alerts yet.")
        path = f"/investigation/{row['incident_id']}" if row["incident_id"] else "/alerts"
        return Interpretation(True, "open_latest_alert", f"Open the latest alert: {row['title']}",
                              action={"type": "navigate", "path": path, "alert_id": row["id"]},
                              answer=f"Opening the latest {row['severity']} alert: {row['title']}.", data=dict(row))

    # ------------------------------------------------------- zoom latest event
    if re.search(r"\b(zoom|fly|go|take me|pan|centre|center|show)\b.*\b(latest|last|newest|most recent)\b.*\b(event|incident|anomal|detection|fire)", s):
        industrial = "industrial" in s
        q = """
            SELECT c.id, c.center_latitude AS lat, c.center_longitude AS lon, c.classification, c.end_time,
                   i.id AS incident_id, f.name AS facility_name
              FROM thermal_clusters c
              LEFT JOIN incidents i ON i.cluster_id = c.id
              LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id AND c.industrial_association
             WHERE c.status = 'active'
        """
        params = {}
        if industrial:
            q += " AND c.classification = ANY(CAST(:classes AS text[]))"
            params["classes"] = INDUSTRIAL_CLASSES
        row = conn.execute(text(q + " ORDER BY c.end_time DESC LIMIT 1"), params).mappings().one_or_none()
        what = "industrial thermal event" if industrial else "thermal event"
        if not row:
            return Interpretation(True, "zoom_latest_event", f"Zoom to the latest {what}", answer=f"No active {what} is stored.")
        label = CLASSES.get(row["classification"], row["classification"])
        where = f" at {row['facility_name']}" if row["facility_name"] else ""
        return Interpretation(
            True, "zoom_latest_event", f"Zoom to the latest {what}",
            action={"type": "focus", "lon": row["lon"], "lat": row["lat"], "zoom": 12, "cluster_id": row["id"],
                    "incident_id": row["incident_id"], "path": "/dashboard"},
            answer=f"Zooming to the latest {what}: {label}{where}.", data={k: row[k] for k in ("id", "lat", "lon", "end_time")},
        )

    # ------------------------------------------------------------- briefing
    if re.search(r"\b(briefing|brief me|situation|summary|status report|sitrep)\b", s):
        from app.voice.briefing import build_briefing

        b = build_briefing(conn, 24)
        return Interpretation(True, "briefing", "Situation briefing (last 24 hours)", answer=b["text"], data=b["facts"])

    # ------------------------------------------------------ incidents (+filters)
    if "incident" in s or re.search(r"\bevents?\b", s):
        prio = _priority(s)
        ftype = _facility_type(s) if re.search(r"\b(near|at|around|close to|by|from)\b", s) or _facility_type(s) else None
        params = []
        parts = []
        if prio:
            params.append(f"min_priority={prio}")
            parts.append(f"{prio}+ priority")
        if "industrial" in s:
            params.append("classification=" + ",".join(INDUSTRIAL_CLASSES))
            parts.append("industrial")
        if ftype:
            params.append(f"facility_type={ftype}")
            parts.append(f"near {FACILITY_TYPES[ftype].lower()}s")
        if re.search(r"\b(show|list|display|open|find|which)\b", s) or params:
            path = "/incidents" + ("?" + "&".join(params) if params else "")
            desc = "Show " + (" ".join(p for p in parts if "near" not in p) + " incidents").strip()
            if ftype:
                desc += f" near {FACILITY_TYPES[ftype].lower()}s"
            return Interpretation(True, "show_incidents", desc, action={"type": "navigate", "path": path})

    # -------------------------------------------------------- active anomalies
    if re.search(r"\b(show|display|view|see)\b.*\b(anomal|detection|hotspot|fires?|heat)", s):
        n = conn.execute(text("SELECT count(*) FROM thermal_observations WHERE acquired_at >= now() - interval '24 hours'")).scalar_one()
        return Interpretation(
            True, "show_active_anomalies", "Show thermal anomalies from the last 24 hours on the map",
            action={"type": "navigate", "path": "/dashboard?hours=24&layers=hotspots"},
            answer=f"Showing {n} thermal detection{'s' if n != 1 else ''} from the last 24 hours.", data={"detections_24h": n},
        )

    # ------------------------------------------------------------ facilities
    ftype = _facility_type(s)
    if ftype and re.search(r"\b(show|list|display|find)\b", s):
        return Interpretation(True, "show_facilities", f"Show {FACILITY_TYPES[ftype].lower()}s",
                              action={"type": "navigate", "path": f"/facilities?type={ftype}"})

    # ------------------------------------------------------------ navigation
    m = re.search(r"\b(?:open|go to|show|navigate to|take me to|switch to)\s+(?:the\s+)?(.+?)(?:\s+page|\s+view|\s+tab)?$", s)
    if m and m.group(1) in PAGES:
        return Interpretation(True, "navigate", f"Open {m.group(1)}", action={"type": "navigate", "path": PAGES[m.group(1)]})

    # ------------------------------------------------------------ zoom to place
    m = re.search(r"\b(?:zoom|fly|go|pan|take me|navigate|centre|center)\s+(?:in\s+)?(?:to|on)\s+(.+)$", s)
    if m:
        place = m.group(1).strip()
        from app.search.service import search_places

        hits = search_places(conn, place, limit=1)
        if hits:
            h = hits[0]
            return Interpretation(
                True, "zoom_to_place", f"Zoom to {h['label']}",
                action={"type": "focus", "lon": h["lon"], "lat": h["lat"], "zoom": h.get("zoom", 11), "path": "/dashboard"},
                answer=f"Zooming to {h['label']}.", data=h,
            )
        return Interpretation(True, "zoom_to_place", f"Zoom to {place}", answer=f"I couldn't find \"{place}\" inside India's monitoring area.")

    return _unsupported(raw)
