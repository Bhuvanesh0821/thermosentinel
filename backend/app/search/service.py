"""Unified search: facilities, incidents, alerts and locations.

Locations resolve from typed coordinates ("22.34, 69.87") or the OpenStreetMap Nominatim
geocoder (usage policy respected: identifying User-Agent, <= 1 request/s, results cached).
Every location result is clipped to India's monitoring area.
"""

from __future__ import annotations

import re
import threading
import time
from functools import lru_cache

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.analytics.classifier import CLASSES
from app.config import get_settings
from app.geo.boundary import get_monitoring_area
from app.ingestion.facilities.classify import FACILITY_TYPES

_COORD = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_REF = re.compile(r"^\s*inc-?0*(\d+)\s*$", re.IGNORECASE)
_geocode_lock = threading.Lock()
_last_geocode = 0.0


def _like(q: str) -> str:
    return "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"


def search_facilities(conn: Connection, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT id, name, operator, facility_type, latitude, longitude, source_ref
              FROM industrial_facilities
             WHERE is_active AND (name ILIKE :q OR operator ILIKE :q)
             ORDER BY (lower(name) = lower(:raw)) DESC, (name ILIKE :prefix) DESC, length(name), id
             LIMIT :limit
            """
        ),
        {"q": _like(q), "raw": q, "prefix": q.replace("%", "") + "%", "limit": limit},
    ).mappings().all()
    return [
        {
            "kind": "facility",
            "id": r["id"],
            "label": r["name"] or f"Unnamed {FACILITY_TYPES.get(r['facility_type'], '').lower()}",
            "detail": FACILITY_TYPES.get(r["facility_type"], r["facility_type"]) + (f" · {r['operator']}" if r["operator"] else ""),
            "lat": r["latitude"],
            "lon": r["longitude"],
            "zoom": 13,
            "source_ref": r["source_ref"],
        }
        for r in rows
    ]


def search_incidents(conn: Connection, q: str, limit: int) -> list[dict]:
    m = _REF.match(q)
    if m:
        where, params = "i.id = :id", {"id": int(m.group(1))}
    else:
        where, params = "(i.title ILIKE :q OR f.name ILIKE :q)", {"q": _like(q)}
    rows = conn.execute(
        text(
            f"""
            SELECT i.id, i.title, i.priority, i.status, i.classification, i.latitude, i.longitude, i.last_detected_at
              FROM incidents i LEFT JOIN industrial_facilities f ON f.id = i.facility_id
             WHERE {where}
             ORDER BY (i.status <> 'closed') DESC, i.risk_score DESC LIMIT :limit
            """
        ),
        {**params, "limit": limit},
    ).mappings().all()
    return [
        {
            "kind": "incident",
            "id": r["id"],
            "label": f"INC-{r['id']:06d} · {r['title']}",
            "detail": f"{r['priority']} · {r['status']} · {CLASSES.get(r['classification'], r['classification'])}",
            "priority": r["priority"],
            "lat": r["latitude"],
            "lon": r["longitude"],
        }
        for r in rows
    ]


def search_alerts(conn: Connection, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT id, incident_id, title, severity, status, latitude, longitude
              FROM alerts WHERE title ILIKE :q OR description ILIKE :q
             ORDER BY (status <> 'resolved') DESC, last_triggered_at DESC LIMIT :limit
            """
        ),
        {"q": _like(q), "limit": limit},
    ).mappings().all()
    return [
        {"kind": "alert", "id": r["id"], "incident_id": r["incident_id"], "label": r["title"],
         "detail": f"{r['severity']} · {r['status']}", "priority": r["severity"], "lat": r["latitude"], "lon": r["longitude"]}
        for r in rows
    ]


@lru_cache(maxsize=512)
def _geocode(q: str) -> tuple:
    global _last_geocode
    settings = get_settings()
    bbox = settings.bbox
    with _geocode_lock:  # Nominatim policy: at most 1 request per second
        wait = 1.05 - (time.monotonic() - _last_geocode)
        if wait > 0:
            time.sleep(wait)
        _last_geocode = time.monotonic()
        try:
            r = httpx.get(
                settings.geocoder_url,
                params={
                    "q": q, "format": "jsonv2", "limit": 5, "bounded": 1,
                    "viewbox": f"{bbox.west},{bbox.north},{bbox.east},{bbox.south}",
                },
                headers={"User-Agent": settings.http_user_agent},
                timeout=10,
            )
            r.raise_for_status()
            return tuple((float(x["lat"]), float(x["lon"]), x.get("display_name", q), x.get("addresstype") or x.get("type")) for x in r.json())
        except (httpx.HTTPError, ValueError, KeyError):
            return ()


def search_locations(q: str, limit: int) -> list[dict]:
    area = get_monitoring_area()
    m = _COORD.match(q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        inside = area.contains(lat, lon)
        return [{"kind": "location", "label": f"{lat:.4f}, {lon:.4f}", "detail": "Coordinates" if inside else "Coordinates outside India's monitoring area",
                 "lat": lat, "lon": lon, "zoom": 11, "inside": inside}] if inside else []
    settings = get_settings()
    if not settings.geocoder_enabled or len(q.strip()) < 3:
        return []
    out = []
    for lat, lon, name, kind in _geocode(q.strip().lower()):
        if area.contains(lat, lon):
            zoom = {"city": 10, "town": 11, "village": 12, "state": 6, "district": 8}.get(kind or "", 10)
            out.append({"kind": "location", "label": name.split(",")[0], "detail": name, "lat": lat, "lon": lon, "zoom": zoom})
        if len(out) >= limit:
            break
    return out


def search_places(conn: Connection, q: str, limit: int = 1) -> list[dict]:
    """Resolve a place for voice 'zoom to X': facilities first, then coordinates/geocoder."""
    return (search_facilities(conn, q, limit) or search_locations(q, limit))[:limit]


def search(conn: Connection, q: str, types: set[str], limit: int) -> dict:
    q = q.strip()
    out: dict[str, list] = {}
    if "facilities" in types:
        out["facilities"] = search_facilities(conn, q, limit)
    if "incidents" in types:
        out["incidents"] = search_incidents(conn, q, limit)
    if "alerts" in types:
        out["alerts"] = search_alerts(conn, q, limit)
    if "locations" in types:
        out["locations"] = search_locations(q, limit)
    return out
