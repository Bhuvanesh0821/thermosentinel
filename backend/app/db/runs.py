"""Ingestion / analysis run bookkeeping (ingestion_runs table)."""

from __future__ import annotations

import json

from sqlalchemy import text

from app.db.engine import transaction


def close_orphaned_runs() -> int:
    """Mark runs left 'running' by a stopped/crashed process as failed.

    Call only while holding the pipeline job lease: no other pipeline job can then be alive,
    so any 'running' row is an orphan.
    """
    with transaction() as conn:
        return (
            conn.execute(
                text(
                    "UPDATE ingestion_runs SET status = 'failed', finished_at = now(), "
                    "error = coalesce(error, 'Aborted: the process stopped before the run completed') "
                    "WHERE status = 'running'"
                )
            ).rowcount
            or 0
        )


def start_run(job: str, source_id: str | None = None, params: dict | None = None) -> int:
    with transaction() as conn:
        return conn.execute(
            text(
                "INSERT INTO ingestion_runs (job, source_id, params) "
                "VALUES (:job, :source_id, CAST(:params AS jsonb)) RETURNING id"
            ),
            {"job": job, "source_id": source_id, "params": json.dumps(params or {}, default=str)},
        ).scalar_one()


def finish_run(
    run_id: int,
    status: str,
    *,
    fetched: int = 0,
    valid: int = 0,
    inserted: int = 0,
    updated: int = 0,
    rejected: int = 0,
    details: dict | None = None,
    error: str | None = None,
) -> None:
    if status in ("failed", "partial"):
        from app.core.observability import record_failure

        record_failure("ingestion", f"run {run_id} {status}: {error or 'see run details'}")
    with transaction() as conn:
        conn.execute(
            text(
                """
                UPDATE ingestion_runs
                   SET status = :status, finished_at = now(),
                       records_fetched = :fetched, records_valid = :valid,
                       records_inserted = :inserted, records_updated = :updated,
                       records_rejected = :rejected,
                       details = CAST(:details AS jsonb), error = :error
                 WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "status": status,
                "fetched": fetched,
                "valid": valid,
                "inserted": inserted,
                "updated": updated,
                "rejected": rejected,
                "details": json.dumps(details or {}, default=str),
                "error": (error or None) and error[:4000],
            },
        )
