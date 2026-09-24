"""Temporal persistence of thermal activity at a location.

A location is judged against the FIRMS history actually held in the database:

* detection_days - distinct UTC days with >=1 detection within `radius_m` of the cluster
  centre during the lookback window;
* coverage_days  - distinct UTC days for which the database holds FIRMS data for the region
  in the same window (the denominator; we never assume data we do not have).

Categories (never 'persistent' without enough history):
  persistent            detection_days >= min_days AND coverage_days >= min_coverage
                        AND detection_days / coverage_days >= min_ratio
  recurring             detection_days >= 2 (but not persistent)
  insufficient_history  single detection day and coverage_days < min_coverage
  transient             single detection day with adequate coverage
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class PersistenceResult:
    category: str
    detection_days: int
    coverage_days: int
    ratio: float
    explanation: str


def classify_persistence(
    detection_days: int,
    coverage_days: int,
    *,
    radius_m: int,
    min_days_persistent: int,
    min_coverage_days: int,
    min_ratio: float,
) -> PersistenceResult:
    detection_days = max(0, int(detection_days))
    coverage_days = max(detection_days, int(coverage_days))
    ratio = detection_days / coverage_days if coverage_days else 0.0
    basis = f"{detection_days} of {coverage_days} day(s) of FIRMS coverage within {radius_m} m"

    if detection_days >= min_days_persistent and coverage_days >= min_coverage_days and ratio >= min_ratio:
        return PersistenceResult("persistent", detection_days, coverage_days, ratio, f"Detected on {basis} ({ratio:.0%}).")
    if detection_days >= 2:
        return PersistenceResult("recurring", detection_days, coverage_days, ratio, f"Repeated detections: {basis}.")
    if coverage_days < min_coverage_days:
        return PersistenceResult(
            "insufficient_history",
            detection_days,
            coverage_days,
            ratio,
            f"Only {coverage_days} day(s) of FIRMS history held; at least {min_coverage_days} are needed to judge recurrence.",
        )
    return PersistenceResult("transient", detection_days, coverage_days, ratio, f"Single detection day: {basis}.")


def coverage_days(conn: Connection, lookback_days: int) -> int:
    return int(
        conn.execute(
            text(
                "SELECT count(DISTINCT acq_date) FROM thermal_observations "
                "WHERE acquired_at >= now() - make_interval(days => :d)"
            ),
            {"d": lookback_days},
        ).scalar_one()
    )


def detection_history(conn: Connection, cluster_ids: list[int], radius_m: int, lookback_days: int) -> dict[int, dict]:
    """Per-cluster distinct detection days / first / last detection near the cluster centre."""
    if not cluster_ids:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT c.id,
                   count(DISTINCT o.acq_date) AS detection_days,
                   count(o.id)                AS observations,
                   min(o.acquired_at)         AS first_seen,
                   max(o.acquired_at)         AS last_seen
              FROM thermal_clusters c
              JOIN thermal_observations o
                ON ST_DWithin(o.geom, c.geom, :radius)
               AND o.acquired_at >= now() - make_interval(days => :lookback)
             WHERE c.id = ANY(CAST(:ids AS bigint[]))
             GROUP BY c.id
            """
        ),
        {"ids": cluster_ids, "radius": radius_m, "lookback": lookback_days},
    ).mappings().all()
    return {r["id"]: dict(r) for r in rows}
