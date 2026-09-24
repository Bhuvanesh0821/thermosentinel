"""Pipeline job orchestration shared by the scheduler, the admin API and the CLI."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import text

from app.analytics.pipeline import run_analysis
from app.config import Settings, get_settings
from app.core.audit import record_event
from app.core.events import bus
from app.db.engine import connection, transaction
from app.db.locks import JobBusyError, job_lease
from app.db.runs import close_orphaned_runs
from app.geo.region_sync import sync_monitoring_region
from app.health.registry import ensure_registry
from app.ingestion.facilities.service import ingest_facilities
from app.ingestion.firms.service import ingest_firms

log = logging.getLogger(__name__)

_state_lock = threading.Lock()
_state: dict = {"running": False, "job": None, "started_at": None, "last_finished_at": None, "last_status": None, "last_error": None}


def job_state() -> dict:
    with _state_lock:
        return dict(_state)


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def ensure_data_source_registry() -> None:
    with transaction() as conn:
        ensure_registry(conn)


def facilities_refresh_due(settings: Settings) -> bool:
    """True while any India tile was never loaded, failed last time, or is older than the refresh interval."""
    from app.geo.boundary import get_monitoring_area
    from app.ingestion.facilities.service import _due_tiles

    area = get_monitoring_area()
    region_tiles = [t for t in settings.bbox.tiles(settings.overpass_tile_deg) if area.intersects_bbox(t)]
    return bool(_due_tiles(region_tiles, settings.facilities_refresh_hours, force=False))


def firms_backfill_days(settings: Settings) -> int | None:
    """Backfill history on first run when a MAP_KEY allows it (the public feed is fixed at 7 days)."""
    if settings.firms_mode != "api" or settings.firms_backfill_days <= 0:
        return None
    with connection() as conn:
        has_data = conn.execute(text("SELECT EXISTS (SELECT 1 FROM thermal_observations)")).scalar_one()
    return None if has_data else settings.firms_backfill_days


def run_full_pipeline(
    *,
    include_facilities: bool | None = None,
    include_firms: bool = True,
    include_analysis: bool = True,
    backfill_days: int | None = None,
    trigger: str = "manual",
) -> dict:
    settings = get_settings()
    with job_lease("pipeline"):
        _set_state(running=True, job="pipeline", started_at=datetime.now(timezone.utc), last_error=None)
        bus.publish("pipeline.started", {"trigger": trigger})
        results: dict = {"trigger": trigger}
        try:
            close_orphaned_runs()
            ensure_data_source_registry()
            results["region"] = sync_monitoring_region()
            # FIRMS first (seconds) so real detections reach the map immediately; the slower
            # facility refresh (minutes, when due) follows, and analysis runs on both.
            if include_firms:
                _set_state(job="firms_ingest")
                results["firms"] = ingest_firms(
                    settings, backfill_days=backfill_days if backfill_days is not None else firms_backfill_days(settings)
                )
            if include_facilities is None:
                include_facilities = facilities_refresh_due(settings)
            if include_facilities:
                _set_state(job="facilities_ingest")
                results["facilities"] = ingest_facilities(settings)
            if include_analysis:
                _set_state(job="analysis")
                results["analysis"] = run_analysis(settings)
            _set_state(last_status="success")
            return results
        except Exception as exc:
            _set_state(last_status="failed", last_error=str(exc)[:500])
            raise
        finally:
            _set_state(running=False, job=None, last_finished_at=datetime.now(timezone.utc))
            bus.publish("pipeline.completed", {"trigger": trigger, "status": job_state().get("last_status")})


def minutes_since_last_success(job: str) -> float | None:
    """Minutes since the last successful (or partial) run of `job`, across all instances."""
    with connection() as conn:
        age = conn.execute(
            text(
                "SELECT extract(epoch FROM now() - max(finished_at)) / 60 FROM ingestion_runs "
                "WHERE job = :job AND status IN ('success', 'partial')"
            ),
            {"job": job},
        ).scalar_one()
    return None if age is None else float(age)


def scheduled_cycle() -> None:
    settings = get_settings()
    # Restarts, redeploys and wake-ups each schedule a cycle shortly after start-up. Skip it when
    # FIRMS was fetched recently (by this or another instance) so the upstream API is not
    # re-downloaded needlessly; the next interval runs normally.
    try:
        age = minutes_since_last_success("firms_ingest")
    except Exception:
        age = None  # the pipeline itself will surface database problems
    if age is not None and age < settings.firms_poll_minutes / 2:
        log.info("scheduled cycle skipped: FIRMS fetched recently", extra={"minutes_ago": round(age, 1)})
        return
    try:
        run_full_pipeline(trigger="scheduler")
    except JobBusyError:
        log.info("scheduled cycle skipped: pipeline already running")
    except Exception:
        log.exception("scheduled pipeline cycle failed")


def apply_retention(settings: Settings | None = None) -> dict:
    """Delete detections older than OBSERVATION_RETENTION_DAYS (Neon free tier: 0.5 GB/project)."""
    settings = settings or get_settings()
    with transaction() as conn:
        deleted = conn.execute(
            text("DELETE FROM thermal_observations WHERE acquired_at < now() - make_interval(days => :d)"),
            {"d": settings.observation_retention_days},
        ).rowcount
        pruned_events = conn.execute(
            text("DELETE FROM system_events WHERE created_at < now() - interval '90 days'")
        ).rowcount
    record_event(
        "maintenance.retention",
        f"Retention: removed {deleted} detections older than {settings.observation_retention_days} days",
        source="maintenance",
        details={"deleted_observations": deleted, "deleted_events": pruned_events},
    )
    return {"deleted_observations": deleted, "deleted_events": pruned_events}
