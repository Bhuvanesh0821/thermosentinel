"""Background scheduler (APScheduler) running the ingestion/analysis cycle."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Settings

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(settings: Settings) -> None:
    global _scheduler
    from app.jobs import apply_retention, scheduled_cycle

    if _scheduler is not None:
        return
    scheduler = BackgroundScheduler(
        timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 900}
    )
    scheduler.add_job(
        scheduled_cycle,
        "interval",
        minutes=settings.firms_poll_minutes,
        id="pipeline_cycle",
        name="FIRMS ingestion + analysis",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=20),
    )
    scheduler.add_job(apply_retention, "cron", hour=3, minute=17, id="retention", name="Data retention")
    scheduler.start()
    _scheduler = scheduler
    log.info("scheduler started", extra={"poll_minutes": settings.firms_poll_minutes})


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_info() -> dict:
    if _scheduler is None:
        return {"running": False, "jobs": []}
    return {
        "running": _scheduler.running,
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
                "interval_minutes": (
                    round(j.trigger.interval.total_seconds() / 60) if hasattr(j.trigger, "interval") else None
                ),
            }
            for j in _scheduler.get_jobs()
        ],
    }
