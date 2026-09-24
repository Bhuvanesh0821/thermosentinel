"""Response cache for heavy, read-mostly endpoints (map layers, analytics).

The data behind these endpoints only changes when the pipeline or an operator action runs,
and every such change publishes on the event bus. The bus's publish counter is therefore
part of each cache key: any new event makes older entries unreachable, so the cache never
serves data older than the last change (plus a TTL as a safety net). Bodies are stored
already serialised, bounded by entry count and total size.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from starlette.responses import Response

from app.core.events import bus
from app.core.responses import dumps, utcnow

MAX_ENTRIES = 64
MAX_BYTES = 48 * 1024 * 1024

_lock = threading.Lock()
_store: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_size = 0
stats = {"hits": 0, "misses": 0}


def _key(namespace: str, params: dict, versioned: bool) -> str:
    version = bus.data_version if versioned else 0
    return f"{namespace}|{version}|{json.dumps(params, sort_keys=True, default=str)}"


def cached_ok(
    namespace: str,
    params: dict,
    build: Callable[[], tuple[Any, dict | None]],
    *,
    ttl_s: float = 600,
    versioned: bool = True,
) -> Response:
    """Return the ok-envelope for `build()`, served from cache while the data is unchanged."""
    global _size
    key = _key(namespace, params, versioned)
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] < ttl_s:
            _store.move_to_end(key)
            stats["hits"] += 1
            return Response(hit[1], media_type="application/json", headers={"X-Cache": "HIT"})
    data, meta = build()
    body = dumps({"status": "ok", "data": data, "meta": {**(meta or {}), "generated_at": utcnow().isoformat()}}).encode()
    with _lock:
        stats["misses"] += 1
        old = _store.pop(key, None)
        if old:
            _size -= len(old[1])
        _store[key] = (now, body)
        _size += len(body)
        while _store and (len(_store) > MAX_ENTRIES or _size > MAX_BYTES):
            _, (_, evicted) = _store.popitem(last=False)
            _size -= len(evicted)
    return Response(body, media_type="application/json", headers={"X-Cache": "MISS"})


def cache_info() -> dict:
    with _lock:
        return {"entries": len(_store), "bytes": _size, **stats}
