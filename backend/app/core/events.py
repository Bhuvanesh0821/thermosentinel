"""In-process event bus feeding the Server-Sent Events stream.

Pipeline jobs run in worker threads; they publish through `bus.publish`, which hands the
message to the asyncio loop thread-safely. Every event is also persisted in
`system_events` by the caller where it matters for auditability.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self.last_event: dict | None = None
        self.published = 0
        # Advances whenever stored data may have changed (completed steps, alert/operator
        # actions) but not on progress/started notices; response caches key on it.
        self.data_version = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def bound(self) -> bool:
        return self._loop is not None and not self._loop.is_closed()

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        message = {
            "type": event_type,
            "payload": payload or {},
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.last_event = {"type": event_type, "at": message["at"]}
        self.published += 1
        if not event_type.endswith((".progress", ".started")):
            self.data_version += 1
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, message)
        except RuntimeError:  # loop shutting down
            pass

    def _fanout(self, message: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.debug("dropping SSE event for slow subscriber")


bus = EventBus()
