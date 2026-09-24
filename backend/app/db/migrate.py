"""Minimal forward-only SQL migration runner.

Migrations live in `database/migrations/NNNN_name.sql` and are applied in order, each in
its own transaction. Applied versions (with a checksum) are recorded in
`schema_migrations`; an edited, already-applied migration is reported, never re-run.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db.engine import get_engine

log = logging.getLogger(__name__)

_FILENAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    filename    text NOT NULL,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


def discover(directory: Path) -> list[tuple[str, Path]]:
    found = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if not match:
            log.warning("skipping unrecognised migration file", extra={"file": path.name})
            continue
        found.append((match.group(1), path))
    versions = [v for v, _ in found]
    if len(versions) != len(set(versions)):
        raise RuntimeError("duplicate migration version numbers detected")
    return found


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def apply_migrations(engine: Engine | None = None, directory: Path | None = None) -> dict:
    engine = engine or get_engine()
    directory = directory or get_settings().migrations_dir
    migrations = discover(directory)

    raw = engine.raw_connection()
    try:
        dbapi = raw.driver_connection  # psycopg.Connection
        with dbapi.cursor() as cur:
            cur.execute(_BOOTSTRAP)
            dbapi.commit()
            cur.execute("SELECT version, checksum FROM schema_migrations")
            applied = {row[0]: row[1] for row in cur.fetchall()}

        newly_applied: list[str] = []
        drifted: list[str] = []
        for version, path in migrations:
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            if version in applied:
                if applied[version] != checksum:
                    drifted.append(path.name)
                continue
            log.info("applying migration", extra={"migration": path.name})
            try:
                with dbapi.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
                        (version, path.name, checksum),
                    )
                dbapi.commit()
            except Exception:
                dbapi.rollback()
                log.exception("migration failed", extra={"migration": path.name})
                raise
            newly_applied.append(path.name)

        if drifted:
            log.warning("applied migrations were modified after being applied", extra={"files": drifted})
        return {
            "applied": newly_applied,
            "already_applied": sorted(applied),
            "drifted": drifted,
            "total": len(migrations),
        }
    finally:
        raw.close()
