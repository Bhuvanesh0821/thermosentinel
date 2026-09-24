"""Shared HTTP client with a descriptive User-Agent and bounded retries."""

from __future__ import annotations

import logging
import time

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def build_client(timeout: float = 90.0) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=20.0),
        headers={"User-Agent": get_settings().http_user_agent},
        follow_redirects=True,
    )


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    backoff_s: float = 3.0,
    log_url: str | None = None,
    **kwargs,
) -> httpx.Response:
    """Perform a request, retrying transient failures. `log_url` masks secrets in logs."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code in RETRYABLE_STATUS and attempt < attempts:
                log.warning(
                    "retryable HTTP status",
                    extra={"url": log_url or url, "status": response.status_code, "attempt": attempt},
                )
                time.sleep(backoff_s * attempt)
                continue
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            log.warning(
                "HTTP transport error",
                extra={"url": log_url or url, "error": str(exc), "attempt": attempt},
            )
            if attempt < attempts:
                time.sleep(backoff_s * attempt)
    assert last_exc is not None
    from app.core.observability import record_failure

    record_failure("external_source", f"{method} {log_url or url}: {last_exc}")
    raise last_exc
