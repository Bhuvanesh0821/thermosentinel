"""System event log (system_events table) + live publication to the SSE bus."""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from app.core.events import bus
from app.db.engine import transaction

log = logging.getLogger(__name__)


def record_event(
    event_type: str,
    message: str,
    *,
    severity: str = "info",
    source: str | None = None,
    details: dict | None = None,
    publish: bool = True,
) -> None:
    details = details or {}
    try:
        with transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO system_events (event_type, severity, source, message, details) "
                    "VALUES (:t, :sev, :src, :msg, CAST(:details AS jsonb))"
                ),
                {"t": event_type, "sev": severity, "src": source, "msg": message, "details": json.dumps(details, default=str)},
            )
    except Exception:  # never let audit logging break a pipeline
        log.exception("failed to persist system event", extra={"event_type": event_type})
    if publish:
        bus.publish(event_type, {"message": message, "severity": severity, "source": source, **details})
