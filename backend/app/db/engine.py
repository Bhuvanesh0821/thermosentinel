"""SQLAlchemy engine for Neon PostgreSQL (psycopg 3 driver).

Neon notes:
* Connections require TLS (`sslmode=require` in the Neon connection string).
* Idle computes suspend after a few minutes, so pooled connections are pre-pinged and
  recycled well before Neon closes them.
* Server-side prepared statements are disabled (`prepare_threshold=None`) so the same
  code works with both the direct and the pooled (PgBouncer) Neon endpoints.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.config import get_settings
from app.core.errors import DatabaseNotConfiguredError

log = logging.getLogger(__name__)

_engine: Engine | None = None
_engine_lock = threading.Lock()


def _normalise_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def db_configured() -> bool:
    return bool(get_settings().database_url_value)


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    settings = get_settings()
    url = settings.database_url_value
    if not url:
        raise DatabaseNotConfiguredError()
    with _engine_lock:
        if _engine is None:
            _engine = create_engine(
                _normalise_url(url),
                pool_pre_ping=True,
                pool_recycle=240,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=30,
                connect_args={
                    "prepare_threshold": None,
                    "connect_timeout": 20,
                    "application_name": "thermosentinel",
                },
            )
            log.info("database engine created")
    return _engine


def dispose_engine() -> None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None


@contextmanager
def transaction() -> Iterator[Connection]:
    """A connection inside a single transaction (commit on success, rollback on error)."""
    with get_engine().begin() as conn:
        yield conn


@contextmanager
def connection() -> Iterator[Connection]:
    """A read-oriented connection (autobegin; rolled back on close)."""
    with get_engine().connect() as conn:
        yield conn


def ping() -> dict:
    """Live connectivity check with latency and server/PostGIS versions."""
    started = time.perf_counter()
    with connection() as conn:
        row = conn.execute(
            text(
                "SELECT current_setting('server_version') AS server_version, "
                "current_database() AS database, "
                "(SELECT extversion FROM pg_extension WHERE extname = 'postgis') AS postgis_version"
            )
        ).mappings().one()
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return {**dict(row), "latency_ms": latency_ms}
