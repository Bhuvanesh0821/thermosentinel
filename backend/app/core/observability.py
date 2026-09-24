"""Failure tracking for production observability.

Every failure path calls `record_failure(category, message)`: the event is logged (structured
JSON in production) and counted in-process, so `/api/system/health` can report recent failures
per category without an external metrics stack. Counters reset on restart; the durable audit
trail stays in `system_events` / `ingestion_runs`.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

log = logging.getLogger("thermosentinel.observability")

CATEGORIES = {
    "ingestion": "Data ingestion",
    "external_source": "External data sources",
    "database": "Database",
    "api": "API requests",
    "alerts": "Alert generation",
    "notifications": "Notification delivery",
    "realtime": "Real-time connections",
}

_SECRET_PATTERNS = [
    re.compile(r"(postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:)[^@\s]+@", re.I),  # connection-string passwords
    re.compile(r"((?:MAP_KEY|map_key|api_key|token|password)[=:/]\s*)[^&\s/]+", re.I),
    re.compile(r"(/(?:area|country|data_availability|kml_fire_footprints)/(?:csv|kml)/)[^/\s]+", re.I),  # FIRMS MAP_KEY in path
]
_lock = threading.Lock()
_started_at = datetime.now(timezone.utc)
_events: dict[str, deque] = {c: deque(maxlen=200) for c in CATEGORIES}
_totals: dict[str, int] = {c: 0 for c in CATEGORIES}


def redact(message: str) -> str:
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(r"\1***", message)
    return message


def record_failure(category: str, message: str, **context) -> None:
    if category not in CATEGORIES:
        category = "api"
    message = redact(str(message))[:400]
    now = datetime.now(timezone.utc)
    with _lock:
        _events[category].append((now, message))
        _totals[category] += 1
    log.error("failure recorded", extra={"category": category, "error": message, **context})


def failure_summary(window_hours: int = 24) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with _lock:
        categories = []
        for key, label in CATEGORIES.items():
            recent = [e for e in _events[key] if e[0] >= cutoff]
            last = _events[key][-1] if _events[key] else None
            categories.append(
                {
                    "key": key,
                    "label": label,
                    "recent": len(recent),
                    "total_since_start": _totals[key],
                    "last_at": last[0] if last else None,
                    "last_error": last[1] if last else None,
                }
            )
    return {"window_hours": window_hours, "since": _started_at, "categories": categories}
