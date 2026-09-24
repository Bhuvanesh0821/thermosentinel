"""ST-DBSCAN clustering on real FIRMS detections."""

import numpy as np
import pandas as pd

from app.analytics.clustering import ClusteringParams, st_dbscan, summarize_clusters, to_epoch_seconds
from app.geo.boundary import get_monitoring_area
from app.geo.distance import haversine_km
from app.ingestion.firms.parser import parse_firms_csv


def _frame(csv_text):
    obs = parse_firms_csv(csv_text, "VIIRS_SNPP_NRT", region=get_monitoring_area()).observations
    df = pd.DataFrame([o.model_dump() for o in obs])
    df["id"] = np.arange(1, len(df) + 1)
    df["acquired_at"] = pd.to_datetime(df["acquired_at"], utc=True)
    return df


def _labels(df, params):
    t = to_epoch_seconds(df["acquired_at"])
    return st_dbscan(df["latitude"].to_numpy(), df["longitude"].to_numpy(), t, params)


def test_epoch_seconds_are_unit_independent():
    ts = pd.Series(pd.to_datetime(["2026-09-22T06:16:00Z", "2026-09-23T06:16:00Z"], utc=True))
    for unit in ("s", "ms", "us", "ns"):
        secs = to_epoch_seconds(ts.dt.as_unit(unit))
        assert secs[1] - secs[0] == 86400


def test_every_observation_gets_a_cluster(viirs_csv):
    df = _frame(viirs_csv)
    labels = _labels(df, ClusteringParams())
    assert len(labels) == len(df)
    assert (labels >= 0).all()


def test_members_of_a_cluster_are_linked_within_eps(viirs_csv):
    df = _frame(viirs_csv)
    params = ClusteringParams(eps_km=1.5, max_gap_hours=72)
    labels = _labels(df, params)
    for label in np.unique(labels):
        idx = np.where(labels == label)[0]
        if len(idx) < 2:
            continue
        # single-linkage: every member has at least one other member within eps
        lat, lon = df["latitude"].to_numpy()[idx], df["longitude"].to_numpy()[idx]
        for i in range(len(idx)):
            d = haversine_km(lat[i], lon[i], np.delete(lat, i), np.delete(lon, i))
            assert d.min() <= params.eps_km + 1e-6


def test_temporal_gap_splits_colocated_detections(viirs_csv):
    """Algorithm property: identical locations far apart in time must not merge."""
    df = _frame(viirs_csv).head(2).copy()
    df["latitude"] = df["latitude"].iloc[0]
    df["longitude"] = df["longitude"].iloc[0]
    df.loc[df.index[1], "acquired_at"] = df["acquired_at"].iloc[0] + pd.Timedelta(hours=200)
    labels = _labels(df, ClusteringParams(eps_km=1.0, max_gap_hours=72))
    assert labels[0] != labels[1]


def test_summary_statistics(viirs_csv):
    df = _frame(viirs_csv)
    labels = _labels(df, ClusteringParams())
    summaries = summarize_clusters(df, labels)
    assert sum(s["observation_count"] for s in summaries) == len(df)
    for s in summaries:
        assert s["start_time"] <= s["end_time"]
        if s["max_frp"] is not None:
            assert s["avg_frp"] <= s["max_frp"] + 1e-9
        assert 0 <= s["night_fraction"] <= 1
        assert get_monitoring_area().contains(s["center_latitude"], s["center_longitude"]) or s["observation_count"] > 1
