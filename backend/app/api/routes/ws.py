"""WebSocket streams of real backend events.

/ws/stream  every event: pipeline.*, ingestion.*, analysis.*, alert.*, region.*
/ws/alerts  alert events only: alert.created, alert.escalated, alert.acknowledged, alert.resolved

Messages are JSON: {"type": "...", "payload": {...}, "at": "ISO-8601"}. A heartbeat is sent
every 20 s. Browser connections must come from an allowed CORS origin.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.core.events import bus
from app.core.responses import dumps

log = logging.getLogger(__name__)
router = APIRouter(tags=["System"])

HEARTBEAT_S = 20


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:  # non-browser clients (CLI, monitoring)
        return True
    settings = get_settings()
    allowed = set(settings.cors_origin_list)
    host = ws.headers.get("host", "")
    same_origin = origin.split("://", 1)[-1] == host
    return origin in allowed or same_origin


async def _serve(ws: WebSocket, prefix: str | None) -> None:
    if not _origin_allowed(ws):
        from app.core.observability import record_failure

        record_failure("realtime", f"WebSocket origin rejected: {ws.headers.get('origin')}")
        await ws.close(code=1008)
        return
    await ws.accept()
    queue = bus.subscribe()

    async def reader() -> None:
        # Detect disconnects; clients do not need to send anything.
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            while True:
                await ws.receive_text()

    reader_task = asyncio.create_task(reader())
    try:
        await ws.send_text(dumps({"type": "hello", "payload": {"subscribers": bus.subscriber_count, "stream": prefix or "all"}}))
        while not reader_task.done():
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
            except asyncio.TimeoutError:
                await ws.send_text(dumps({"type": "heartbeat", "payload": {}}))
                continue
            if prefix and not message["type"].startswith(prefix):
                continue
            await ws.send_text(dumps(message))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # unexpected send/serialisation failure
        from app.core.observability import record_failure

        record_failure("realtime", f"WebSocket stream error: {type(exc).__name__}: {exc}")
    finally:
        bus.unsubscribe(queue)
        reader_task.cancel()


@router.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await _serve(ws, None)


@router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await _serve(ws, "alert.")
