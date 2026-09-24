"""Sensitivity of ST-DBSCAN clustering to its parameters, on the REAL stored FIRMS detections.

Reads observations from Neon (last CLUSTER_WINDOW_DAYS), re-clusters them in memory for a
grid of (eps_km, max_gap_hours) and reports how cluster counts, sizes and spatial extents
respond. Nothing is written to the database. Use it to justify the chosen defaults.

    backend/.venv/Scripts/python ml/evaluate_clustering.py [--days 10]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.analytics.clustering import ClusteringParams, st_dbscan, summarize_clusters, to_epoch_seconds
from app.db.engine import connection


def load(days: int) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, latitude, longitude, acquired_at, acq_date, frp, brightness, confidence_level,
                       confidence_pct, daynight, instrument, product
                  FROM thermal_observations WHERE acquired_at >= :since
                """
            ),
            {"since": datetime.now(timezone.utc) - timedelta(days=days)},
        ).mappings().all()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["acquired_at"] = pd.to_datetime(df["acquired_at"], utc=True)
    return df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=10)
    args = parser.parse_args()
    df = load(args.days)
    if df.empty:
        print("No stored observations in the window - run the pipeline first.")
        return 1
    t = to_epoch_seconds(df["acquired_at"])
    print(f"{len(df)} real detections, last {args.days} days\n")
    print(f"{'eps_km':>7} {'gap_h':>6} {'clusters':>9} {'multi':>6} {'max_size':>9} {'p95_extent_km':>14}")
    for eps in (0.75, 1.0, 1.5, 2.0, 3.0):
        for gap in (24, 72, 168):
            labels = st_dbscan(df["latitude"].to_numpy(), df["longitude"].to_numpy(), t, ClusteringParams(eps, gap, 1))
            summaries = summarize_clusters(df, labels)
            sizes = np.array([s["observation_count"] for s in summaries])
            extents = np.array([s["extent_radius_m"] for s in summaries]) / 1000
            print(
                f"{eps:7.2f} {gap:6d} {len(summaries):9d} {(sizes > 1).sum():6d} {sizes.max():9d} "
                f"{np.percentile(extents, 95):14.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
