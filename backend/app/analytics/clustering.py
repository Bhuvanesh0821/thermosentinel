"""Spatio-temporal clustering of thermal observations (ST-DBSCAN on a sparse neighbour graph).

Two detections are neighbours when they are within `eps_km` (great-circle distance) AND
within `max_gap_hours` of each other. The sparse neighbour graph is built with a haversine
BallTree and passed to scikit-learn's DBSCAN as a precomputed metric, so memory stays
proportional to the number of true neighbours rather than N^2.

With min_samples=1 (default) every detection belongs to exactly one cluster - an isolated
detection is a valid single-observation event, not noise. With min_samples>1, DBSCAN noise
points are returned as singleton clusters so no real observation is ever dropped.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from shapely.geometry import MultiPoint
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree

from app.geo.distance import EARTH_RADIUS_KM, haversine_km

CONFIDENCE_WEIGHT = {"low": 0.3, "nominal": 0.6, "high": 0.9}


@dataclass(frozen=True)
class ClusteringParams:
    eps_km: float = 1.5
    max_gap_hours: float = 72.0
    min_samples: int = 1


_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


def to_epoch_seconds(times: pd.Series) -> np.ndarray:
    """UTC epoch seconds, independent of the datetime64 unit (pandas 3 may use us/ms, not ns)."""
    return (pd.to_datetime(times, utc=True) - _EPOCH).dt.total_seconds().to_numpy()


def st_dbscan(lat: np.ndarray, lon: np.ndarray, t_seconds: np.ndarray, params: ClusteringParams) -> np.ndarray:
    """Return an integer cluster label for every observation (no -1 labels)."""
    n = len(lat)
    if n == 0:
        return np.array([], dtype=int)
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    t_seconds = np.asarray(t_seconds, dtype=float)

    coords = np.radians(np.column_stack([lat, lon]))
    tree = BallTree(coords, metric="haversine")
    neighbours, distances = tree.query_radius(coords, r=params.eps_km / EARTH_RADIUS_KM, return_distance=True)

    max_gap_s = params.max_gap_hours * 3600.0
    rows, cols, vals = [], [], []
    for i in range(n):
        j = neighbours[i]
        keep = np.abs(t_seconds[j] - t_seconds[i]) <= max_gap_s
        j = j[keep]
        rows.append(np.full(j.shape[0], i, dtype=np.int64))
        cols.append(j.astype(np.int64))
        # +1e-9 keeps zero distances (co-located detections) as explicit graph edges.
        vals.append(distances[i][keep] * EARTH_RADIUS_KM + 1e-9)

    graph = csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # EfficiencyWarning about unsorted precomputed graphs
        labels = DBSCAN(eps=params.eps_km, min_samples=params.min_samples, metric="precomputed").fit_predict(graph)

    noise = labels == -1
    if noise.any():
        start = labels.max() + 1 if (~noise).any() else 0
        labels[noise] = np.arange(start, start + int(noise.sum()))
    return labels


def _confidence_value(level, pct) -> float | None:
    if pct is not None and not pd.isna(pct):
        return float(pct) / 100.0
    if isinstance(level, str):
        return CONFIDENCE_WEIGHT.get(level)
    return None


def summarize_clusters(df: pd.DataFrame, labels: np.ndarray) -> list[dict]:
    """Aggregate per-cluster statistics. `df` needs columns:
    id, latitude, longitude, acquired_at (tz-aware), acq_date, frp, brightness,
    confidence_level, confidence_pct, daynight, instrument, product."""
    if df.empty:
        return []
    work = df.copy()
    work["label"] = labels
    work["conf"] = [
        _confidence_value(lvl, pct) for lvl, pct in zip(work["confidence_level"], work["confidence_pct"])
    ]
    out: list[dict] = []
    for label, g in work.groupby("label", sort=False):
        lats = g["latitude"].to_numpy(dtype=float)
        lons = g["longitude"].to_numpy(dtype=float)
        frp = pd.to_numeric(g["frp"], errors="coerce").to_numpy(dtype=float)
        frp_valid = frp[~np.isnan(frp)]
        weights = np.where(np.isnan(frp), 0.0, frp)
        if weights.sum() > 0:
            c_lat = float(np.average(lats, weights=weights))
            c_lon = float(np.average(lons, weights=weights))
        else:
            c_lat, c_lon = float(lats.mean()), float(lons.mean())
        extent_m = float(haversine_km(c_lat, c_lon, lats, lons).max() * 1000.0) if len(lats) > 1 else 0.0
        hull = MultiPoint(list(zip(lons, lats))).convex_hull if len(lats) > 1 else None
        start, end = g["acquired_at"].min(), g["acquired_at"].max()
        conf = pd.to_numeric(g["conf"], errors="coerce").dropna()
        bright = pd.to_numeric(g["brightness"], errors="coerce").dropna()
        out.append(
            {
                "label": int(label),
                "member_ids": g["id"].astype("int64").tolist(),
                "center_latitude": round(c_lat, 6),
                "center_longitude": round(c_lon, 6),
                "extent_radius_m": round(extent_m, 1),
                "hull_wkt": hull.wkt if hull is not None and not hull.is_empty else None,
                "observation_count": int(len(g)),
                "max_frp": float(frp_valid.max()) if frp_valid.size else None,
                "avg_frp": float(frp_valid.mean()) if frp_valid.size else None,
                "total_frp": float(frp_valid.sum()) if frp_valid.size else None,
                "max_brightness": float(bright.max()) if not bright.empty else None,
                "start_time": start.to_pydatetime(),
                "end_time": end.to_pydatetime(),
                "duration_hours": round((end - start).total_seconds() / 3600.0, 2),
                "detection_days": int(g["acq_date"].nunique()),
                "night_fraction": round(float((g["daynight"] == "N").mean()), 3),
                "mean_confidence": round(float(conf.mean()), 3) if not conf.empty else None,
                "instruments": sorted({str(v) for v in g["instrument"].dropna()}),
                "products": sorted({str(v) for v in g["product"].dropna()}),
            }
        )
    return out
