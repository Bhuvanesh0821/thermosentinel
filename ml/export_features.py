"""Export per-cluster evidence features + engine assessments to CSV (real stored data only).

This is the training/evaluation table for a future supervised classifier (Stage 2+): once
analysts label incidents (e.g. confirmed flare / agricultural burn / false positive), a model
can be trained on exactly the features the rule-based engine already uses, and compared with it.

    backend/.venv/Scripts/python ml/export_features.py [--out ml/exports/cluster_features.csv]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
import pandas as pd
from sqlalchemy import text

from app.db.engine import connection

QUERY = """
SELECT c.id AS cluster_id, c.status, c.center_latitude, c.center_longitude, c.observation_count,
       c.max_frp, c.avg_frp, c.total_frp, c.max_brightness, c.duration_hours, c.detection_days,
       c.night_fraction, c.mean_confidence, c.extent_radius_m,
       c.persistence_category, c.persistence_detection_days, c.persistence_coverage_days, c.persistence_ratio,
       c.spatial_relationship, c.nearest_facility_distance_m, c.facility_member_share,
       f.facility_type AS nearest_facility_type,
       lc.dominant_class_name AS land_cover_dominant, lc.class_fractions,
       c.classification, c.evidence_strength, c.risk_score, c.priority, c.analysis_version,
       c.start_time, c.end_time
  FROM thermal_clusters c
  LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id
  LEFT JOIN land_cover lc ON lc.id = c.land_cover_id
 ORDER BY c.id
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).parent / "exports" / "cluster_features.csv"))
    args = parser.parse_args()
    with connection() as conn:
        df = pd.DataFrame([dict(r) for r in conn.execute(text(QUERY)).mappings()])
    if df.empty:
        print("No clusters stored yet - run the pipeline first.")
        return 1
    fractions = pd.json_normalize(df.pop("class_fractions").apply(lambda v: v or {})).add_prefix("lc_frac_")
    df = pd.concat([df, fractions], axis=1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} clusters x {df.shape[1]} columns to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
