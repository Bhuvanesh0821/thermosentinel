"""System health and data-source status."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.core.events import bus
from app.db.engine import connection, db_configured, ping
from app.health.registry import DATA_SOURCES

log = logging.getLogger(__name__)

_probe_cache: dict[str, tuple[float, dict]] = {}
_probe_lock = threading.Lock()
PROBE_TTL_S = 600


def _probe_tile(source_id: str) -> dict:
    """Check an imagery tile service is reachable (cached for PROBE_TTL_S)."""
    now = time.time()
    with _probe_lock:
        cached = _probe_cache.get(source_id)
        if cached and now - cached[0] < PROBE_TTL_S:
            return cached[1]
    day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    url = {
        "nasa_gibs": f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/{day}/GoogleMapsCompatible_Level9/4/6/11.jpg",
        "eox_s2cloudless": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/4/6/11.jpg",
    }[source_id]
    checked_at = datetime.now(timezone.utc)
    try:
        started = time.perf_counter()
        r = httpx.get(url, timeout=6, headers={"User-Agent": get_settings().http_user_agent})
        latency = round((time.perf_counter() - started) * 1000)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
        result = {
            "status": "connected" if ok else "degraded",
            "status_message": f"Tile service responded HTTP {r.status_code} in {latency} ms",
            "last_success_at": checked_at if ok else None,
            "last_attempt_at": checked_at,
        }
    except httpx.HTTPError as exc:
        result = {
            "status": "unavailable",
            "status_message": f"Tile service unreachable: {exc.__class__.__name__}",
            "last_success_at": None,
            "last_attempt_at": checked_at,
        }
    with _probe_lock:
        _probe_cache[source_id] = (now, result)
    return result


def _boundary_status(source_id: str) -> dict:
    from app.geo.boundary import get_monitoring_area

    try:
        area = get_monitoring_area()
    except Exception as exc:
        return {"status": "unavailable", "status_message": f"Boundary file could not be loaded: {exc}"}
    props = area.properties.get("land" if source_id == "ne_india_boundary" else "monitoring_area", {})
    detail = (
        f"Natural Earth {props.get('source_version', '')}".strip()
        if source_id == "ne_india_boundary"
        else "Mainland + Andaman & Nicobar EEZ"
    )
    return {
        "status": "connected",
        "status_message": f"{detail}; loaded from repository file, clipping all ingestion",
        "last_success_at": props.get("retrieved_at"),
        "last_attempt_at": props.get("retrieved_at"),
    }


def database_status() -> dict:
    if not db_configured():
        return {"status": "not_configured", "message": "DATABASE_URL is not set"}
    try:
        info = ping()
        postgis = info.get("postgis_version")
        return {
            "status": "connected" if postgis else "degraded",
            "message": (
                f"PostgreSQL {info['server_version']} / PostGIS {postgis}"
                if postgis
                else f"PostgreSQL {info['server_version']} (PostGIS not installed - run migrations)"
            ),
            **info,
        }
    except Exception as exc:
        from app.core.observability import record_failure

        record_failure("database", f"ping failed: {type(exc).__name__}: {exc}")
        return {"status": "unavailable", "message": f"Database unreachable: {exc.__class__.__name__}"}


def health() -> dict:
    from app.jobs import job_state
    from app.scheduler import scheduler_info

    settings = get_settings()
    db = database_status()
    overall = "ok" if db["status"] == "connected" else "degraded"
    return {
        "status": overall,
        "version": __version__,
        "environment": settings.app_env,
        "data_mode": settings.data_mode,
        # "open": the UI may start a pipeline run; "restricted": operators need X-Admin-Token.
        "pipeline_trigger": "restricted" if (settings.admin_token_value or settings.is_production) else "open",
        "time": datetime.now(timezone.utc),
        "region": {"name": settings.region_name, "bbox": settings.bbox.as_list()},
        "database": db,
        "firms_mode": settings.firms_mode,
        "scheduler": scheduler_info(),
        "pipeline": job_state(),
        "live_stream_subscribers": bus.subscriber_count,
    }


_STARTED_AT = datetime.now(timezone.utc)


def _age_h(ts) -> float | None:
    if not ts:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600


def system_health() -> dict:
    """Component-level status (connected / degraded / unavailable) from live checks."""
    from app.notifications.service import channel_status
    from app.scheduler import scheduler_info

    settings = get_settings()
    sources = {s["id"]: s for s in data_sources()}
    db = sources.get("database", {})
    components: list[dict] = []

    def add(key, label, status, detail, checked_at=None, **extra):
        mapped = {"connected": "connected", "degraded": "degraded"}.get(status, "unavailable")
        components.append({"key": key, "label": label, "status": mapped, "raw_status": status, "detail": detail,
                           "checked_at": checked_at or datetime.now(timezone.utc), **extra})

    uptime_h = (datetime.now(timezone.utc) - _STARTED_AT).total_seconds() / 3600
    add("api", "ThermoSentinel API", "connected", f"v{__version__} · up {uptime_h:.1f} h · {settings.app_env}")
    add("database", "Database (PostgreSQL + PostGIS)",
        db.get("status") if db.get("status") != "connected" or (db.get("latency_ms") or 0) < 2000 else "degraded",
        db.get("status_message") or "", latency_ms=db.get("latency_ms"))

    def source_component(key, sid, label, stale_after_h):
        src = sources.get(sid, {})
        status = src.get("status", "unknown")
        age = _age_h(src.get("last_success_at"))
        detail = src.get("status_message") or "No successful run yet"
        if status == "connected" and age is not None and age > stale_after_h:
            status, detail = "degraded", f"Last success {age:.1f} h ago (expected every {stale_after_h / 3:.0f} h). {detail}"
        if status in ("unknown", "not_configured"):
            status = "unavailable" if db.get("status") != "connected" else "degraded"
        add(key, label, status, detail, last_success_at=src.get("last_success_at"))

    source_component("nasa_firms", "nasa_firms", "NASA FIRMS thermal data", 3 * settings.firms_poll_minutes / 60)
    source_component("industrial", "osm_overpass", "Industrial infrastructure (OSM)", 3 * settings.facilities_refresh_hours)
    source_component("land_cover", "esa_worldcover", "Land cover (ESA WorldCover)", 3 * settings.firms_poll_minutes / 60 * 24)

    stream_status = "connected" if bus.bound else "unavailable"
    last = bus.last_event
    add("realtime", "Real-time stream (WebSocket / SSE)", stream_status,
        f"{bus.subscriber_count} live client(s); last event {last['type']} at {last['at']}" if last else f"{bus.subscriber_count} live client(s); no events yet",
        subscribers=bus.subscriber_count)

    channels = channel_status(settings)
    failing = [c for c in channels if c["status"] == "degraded"]
    configured = [c["label"] for c in channels if c["configured"]]
    add("notifications", "Notification service", "degraded" if failing else "connected",
        ("Failing: " + ", ".join(c["label"] for c in failing) + ". " if failing else "") + "Active channels: " + ", ".join(configured),
        channels=channels)

    sched = scheduler_info()
    add("scheduler", "Pipeline scheduler", "connected" if sched["running"] else ("degraded" if settings.scheduler_enabled else "unavailable"),
        ", ".join(f"{j['name']} next {j['next_run_time']}" for j in sched["jobs"]) or "Scheduler not running", jobs=sched["jobs"])

    worst = "connected"
    if any(c["status"] == "unavailable" for c in components):
        worst = "unavailable"
    elif any(c["status"] == "degraded" for c in components):
        worst = "degraded"
    from app.core.observability import failure_summary

    return {
        "status": worst,
        "environment": settings.app_env,
        "components": components,
        "failures": failure_summary(24),
        "checked_at": datetime.now(timezone.utc),
    }


def data_sources() -> list[dict]:
    settings = get_settings()
    runtime: dict[str, dict] = {}
    latest_runs: dict[str, dict] = {}
    db = database_status()
    if db["status"] in ("connected", "degraded"):
        try:
            with connection() as conn:
                runtime = {
                    r["id"]: dict(r)
                    for r in conn.execute(
                        text(
                            "SELECT id, enabled, status, status_message, last_attempt_at, last_success_at, "
                            "last_error_at, last_error, last_record_count, config FROM data_sources"
                        )
                    ).mappings()
                }
                latest_runs = {
                    r["source_id"]: dict(r)
                    for r in conn.execute(
                        text(
                            """
                            SELECT DISTINCT ON (source_id) source_id, id, job, status, started_at, finished_at,
                                   records_fetched, records_valid, records_inserted, error
                              FROM ingestion_runs WHERE source_id IS NOT NULL
                             ORDER BY source_id, started_at DESC
                            """
                        )
                    ).mappings()
                }
        except Exception as exc:
            log.warning("could not read data source status", extra={"error": str(exc)[:300]})

    out: list[dict] = []
    for src in DATA_SOURCES:
        entry = {**src, "status": "unknown", "status_message": None, "last_success_at": None, "last_attempt_at": None}
        if src["category"] == "imagery":
            entry.update(_probe_tile(src["id"]))
            entry["status_message"] = entry["status_message"] + " (client-side map tiles; not stored)"
        elif src["category"] == "boundary":
            entry.update(_boundary_status(src["id"]))
        else:
            rt = runtime.get(src["id"])
            if rt:
                entry.update({k: v for k, v in rt.items() if k != "id"})
            elif db["status"] not in ("connected", "degraded"):
                entry["status_message"] = "Status unavailable: database not reachable"
            if src["id"] == "nasa_firms":
                entry["mode"] = settings.firms_mode
                entry["map_key_configured"] = settings.firms_map_key is not None
                if entry["status"] == "unknown":
                    entry["status_message"] = entry["status_message"] or "No ingestion has run yet"
            if src["id"] == "esa_worldcover" and not settings.landcover_enabled:
                entry["status"] = "disabled"
            entry["latest_run"] = latest_runs.get(src["id"])
        out.append(entry)

    host = ""
    if settings.database_url_value:
        from sqlalchemy.engine import make_url

        try:
            host = make_url(settings.database_url_value).host or ""
        except Exception:
            host = ""
    is_neon = host.endswith("neon.tech")
    out.append(
        {
            "id": "database",
            # Name the database truthfully: only claim Neon when connected to a Neon endpoint.
            "name": "Neon PostgreSQL + PostGIS" if is_neon or not host else f"PostgreSQL + PostGIS ({host})",
            "category": "database",
            "provider": "Neon" if is_neon or not host else "Self-hosted PostgreSQL",
            "url": "https://neon.tech" if is_neon or not host else None,
            "license": None,
            "description": "Primary datastore for observations, facilities, land cover, clusters, incidents and alerts.",
            "status": db["status"],
            "status_message": db.get("message"),
            "latency_ms": db.get("latency_ms"),
            "last_success_at": datetime.now(timezone.utc) if db["status"] == "connected" else None,
            "last_attempt_at": datetime.now(timezone.utc),
        }
    )
    return out
