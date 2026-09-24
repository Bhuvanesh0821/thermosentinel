"""Notification service with pluggable channels.

Channels
  in_app   always on; stored rows power the notification centre (unread count, mark read).
  browser  delivered client-side: the UI shows an OS/browser notification when the live stream
           announces a new or escalated alert and the user has granted permission.
  webhook  JSON POST to NOTIFY_WEBHOOK_URL (Slack/Teams/automation), >= NOTIFY_WEBHOOK_MIN_SEVERITY.
  email    SMTP (SMTP_HOST/PORT/USERNAME/PASSWORD/FROM, NOTIFY_EMAIL_TO), >= NOTIFY_EMAIL_MIN_SEVERITY.

Only real alerts are ever notified; channels without credentials report `not_configured` and
send nothing. Credentials are read from the server environment and never exposed by the API.
Each (alert, channel, recipient, event) is delivered at most once.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx
from sqlalchemy import text

from app.config import PRIORITY_ORDER, Settings, get_settings
from app.db.engine import connection, transaction

log = logging.getLogger(__name__)
RANK = {p: i for i, p in enumerate(PRIORITY_ORDER)}


def channel_status(settings: Settings | None = None) -> list[dict]:
    """Configuration + last delivery outcome per channel (no secrets)."""
    settings = settings or get_settings()
    last: dict[str, dict] = {}
    try:
        with connection() as conn:
            for r in conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (channel) channel, status, last_error, coalesce(sent_at, created_at) AS at
                      FROM notifications ORDER BY channel, created_at DESC
                    """
                )
            ).mappings():
                last[r["channel"]] = dict(r)
    except Exception:
        pass

    def entry(channel: str, label: str, configured: bool, detail: str, min_sev: str | None = None) -> dict:
        lr = last.get(channel)
        status = "not_configured" if not configured else ("degraded" if lr and lr["status"] == "failed" else "connected")
        return {
            "channel": channel,
            "label": label,
            "configured": configured,
            "status": status,
            "detail": detail,
            "min_severity": min_sev,
            "last_delivery_at": lr["at"] if lr else None,
            "last_delivery_status": lr["status"] if lr else None,
            "last_error": (lr or {}).get("last_error"),
        }

    webhook_host = httpx.URL(settings.notify_webhook_url).host if settings.notify_webhook_url else None
    smtp_ok = bool(settings.smtp_host and settings.smtp_from and settings.email_recipients)
    return [
        entry("in_app", "In-app notification centre", True, "Stored notifications with unread tracking"),
        entry("browser", "Browser notifications", True, "Shown by the dashboard when the user grants permission (client-side)"),
        entry("webhook", "Webhook", bool(webhook_host), f"POST to {webhook_host}" if webhook_host else "Set NOTIFY_WEBHOOK_URL", settings.notify_webhook_min_severity),
        entry(
            "email",
            "Email (SMTP)",
            smtp_ok,
            f"{settings.smtp_host}:{settings.smtp_port} -> {len(settings.email_recipients)} recipient(s)" if smtp_ok else "Set SMTP_HOST, SMTP_FROM and NOTIFY_EMAIL_TO",
            settings.notify_email_min_severity,
        ),
    ]


def create_in_app(conn, alerts: list[dict]) -> int:
    """`alerts`: dicts with id, title, description, severity, event ('created' | 'escalated:<sev>')."""
    if not alerts:
        return 0
    return (
        conn.execute(
            text(
                """
                INSERT INTO notifications (alert_id, channel, recipient, title, body, status, sent_at, event, severity)
                SELECT u.aid, 'in_app', '', u.title, u.body, 'sent', now(), u.event, u.sev
                  FROM unnest(CAST(:aids AS bigint[]), CAST(:titles AS text[]), CAST(:bodies AS text[]),
                              CAST(:events AS text[]), CAST(:sevs AS text[])) AS u(aid, title, body, event, sev)
                ON CONFLICT (alert_id, channel, recipient, event) DO NOTHING
                """
            ),
            {
                "aids": [a["id"] for a in alerts],
                "titles": [a["title"] for a in alerts],
                "bodies": [a["description"] for a in alerts],
                "events": [a["event"] for a in alerts],
                "sevs": [a["severity"] for a in alerts],
            },
        ).rowcount
        or 0
    )


def _record(alert: dict, channel: str, recipient: str, status: str, error: str | None) -> bool:
    """Returns False if this (alert, channel, recipient, event) was already delivered."""
    with transaction() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO notifications (alert_id, channel, recipient, title, body, status, attempts, last_error,
                                           sent_at, event, severity)
                VALUES (:aid, :ch, :rcpt, :title, :body, :status, 1, :err, CASE WHEN :status = 'sent' THEN now() END,
                        :event, :sev)
                ON CONFLICT (alert_id, channel, recipient, event) DO NOTHING
                RETURNING id
                """
            ),
            {
                "aid": alert["id"], "ch": channel, "rcpt": recipient, "title": alert["title"],
                "body": alert["description"], "status": status, "err": error, "event": alert["event"],
                "sev": alert["severity"],
            },
        ).first()
    return row is not None


def _already_sent(alert: dict, channel: str, recipient: str) -> bool:
    with connection() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT 1 FROM notifications WHERE alert_id = :aid AND channel = :ch AND recipient = :r AND event = :e"
                ),
                {"aid": alert["id"], "ch": channel, "r": recipient, "e": alert["event"]},
            ).first()
        )


def _incident_link(settings: Settings, alert: dict) -> str | None:
    return settings.frontend_link(f"/investigation/{alert['incident_id']}") if alert.get("incident_id") else None


def _send_webhook(settings: Settings, alert: dict) -> tuple[str, str | None]:
    payload = {
        "source": "ThermoSentinel",
        "event": alert["event"],
        "alert_id": alert["id"],
        "incident_id": alert.get("incident_id"),
        "severity": alert["severity"],
        "title": alert["title"],
        "description": alert["description"],
        "rules": alert.get("rules"),
        "location": {"lat": alert.get("latitude"), "lon": alert.get("longitude")},
        "url": _incident_link(settings, alert),
        "text": f"[{alert['severity'].upper()}] {alert['title']}",
    }
    try:
        r = httpx.post(settings.notify_webhook_url, json=payload, timeout=15, headers={"User-Agent": settings.http_user_agent})
        return ("sent", None) if r.status_code < 300 else ("failed", f"HTTP {r.status_code}: {r.text[:200]}")
    except httpx.HTTPError as exc:
        return "failed", str(exc)[:300]


def _send_email(settings: Settings, alert: dict, recipient: str) -> tuple[str, str | None]:
    msg = EmailMessage()
    msg["Subject"] = f"[ThermoSentinel · {alert['severity'].upper()}] {alert['title']}"
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    lat, lon = alert.get("latitude"), alert.get("longitude")
    msg.set_content(
        f"{alert['description']}\n\n"
        f"Severity: {alert['severity']}\nRules: {', '.join(alert.get('rules') or [])}\n"
        + (f"Location: {lat:.4f}, {lon:.4f}\n" if lat is not None and lon is not None else "")
        + (f"Investigate: {link}\n" if (link := _incident_link(settings, alert)) else "")
        + "\nInferred from NASA FIRMS satellite detections and open geospatial data; requires verification.\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password_value or "")
            smtp.send_message(msg)
        return "sent", None
    except (smtplib.SMTPException, OSError) as exc:
        return "failed", str(exc)[:300]


def dispatch_external(alerts: list[dict], settings: Settings | None = None) -> dict:
    """Deliver new/escalated alerts to webhook and email channels (when configured)."""
    settings = settings or get_settings()
    stats = {"webhook": 0, "email": 0, "failed": 0}
    for alert in alerts:
        sev = RANK.get(alert["severity"], 0)
        if settings.notify_webhook_url and sev >= RANK[settings.notify_webhook_min_severity]:
            host = httpx.URL(settings.notify_webhook_url).host
            if not _already_sent(alert, "webhook", host):
                status, err = _send_webhook(settings, alert)
                _record(alert, "webhook", host, status, err)
                stats["webhook" if status == "sent" else "failed"] += 1
        if settings.smtp_host and settings.smtp_from and sev >= RANK[settings.notify_email_min_severity]:
            for rcpt in settings.email_recipients:
                if not _already_sent(alert, "email", rcpt):
                    status, err = _send_email(settings, alert, rcpt)
                    _record(alert, "email", rcpt, status, err)
                    stats["email" if status == "sent" else "failed"] += 1
    if stats["failed"]:
        from app.core.observability import record_failure

        record_failure("notifications", f"{stats['failed']} external deliveries failed", **stats)
    return stats
