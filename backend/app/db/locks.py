"""Job leases stored in PostgreSQL.

Session-level advisory locks do not survive Neon's pooled (PgBouncer transaction-mode)
endpoint, so leases are implemented as rows with an expiry instead. A process-local lock
serialises jobs inside one backend process as well.
"""

from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text

from app.core.errors import ConflictError
from app.db.engine import transaction

HOLDER = f"{socket.gethostname()}:{os.getpid()}"
pipeline_lock = threading.Lock()


class JobBusyError(ConflictError):
    code = "job_busy"


@contextmanager
def job_lease(name: str, ttl_minutes: int = 90) -> Iterator[None]:
    if not pipeline_lock.acquire(blocking=False):
        raise JobBusyError(f"Another pipeline job is already running in this process (requested: {name}).")
    try:
        with transaction() as conn:
            acquired = conn.execute(
                text(
                    """
                    INSERT INTO job_locks (name, holder, acquired_at, locked_until)
                    VALUES (:name, :holder, now(), now() + make_interval(mins => :ttl))
                    ON CONFLICT (name) DO UPDATE
                       SET holder = EXCLUDED.holder, acquired_at = now(), locked_until = EXCLUDED.locked_until
                     WHERE job_locks.locked_until < now() OR job_locks.holder = EXCLUDED.holder
                    RETURNING holder
                    """
                ),
                {"name": name, "holder": HOLDER, "ttl": ttl_minutes},
            ).scalar_one_or_none()
        if acquired is None:
            raise JobBusyError(f"Job '{name}' is locked by another process.")
        try:
            yield
        finally:
            with transaction() as conn:
                conn.execute(
                    text("DELETE FROM job_locks WHERE name = :name AND holder = :holder"),
                    {"name": name, "holder": HOLDER},
                )
    finally:
        pipeline_lock.release()
