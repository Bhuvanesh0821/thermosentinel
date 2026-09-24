"""Consistent JSON envelopes.

Success: {"status": "ok", "data": ..., "meta": {...}}
Error:   {"status": "error", "error": {"code", "message", "details"}}

Responses are serialised directly with json.dumps (bypassing jsonable_encoder) because
some map layers carry tens of thousands of features.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from starlette.responses import Response


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default(value: Any):
    if isinstance(value, datetime):
        # Always emit UTC, whatever the database session time zone is.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    if hasattr(value, "item"):  # NumPy scalars
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")


def _clean(value: Any):
    """Replace NaN/inf (invalid JSON) with None, recursively."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def dumps(payload: Any) -> str:
    return json.dumps(_clean(payload), default=_default, separators=(",", ":"), allow_nan=False)


class JSONEnvelopeResponse(Response):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return dumps(content).encode("utf-8")


def ok(data: Any, meta: dict | None = None, status_code: int = 200) -> JSONEnvelopeResponse:
    body = {"status": "ok", "data": data, "meta": {**(meta or {}), "generated_at": utcnow().isoformat()}}
    return JSONEnvelopeResponse(body, status_code=status_code)


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONEnvelopeResponse:
    body = {"status": "error", "error": {"code": code, "message": message, "details": details}}
    return JSONEnvelopeResponse(body, status_code=status_code)
