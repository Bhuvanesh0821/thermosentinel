"""Analysis pipeline: cluster -> proximity -> persistence -> land cover -> intelligence -> incidents.

Cluster identity is kept stable across runs: after re-clustering the analysis window, each
new cluster adopts the id of the previous cluster that contributed most of its detections;
superseded clusters are marked 'merged' and clusters without detections in the window
become 'inactive'.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import text

from app.alerts.service import update_incidents_and_alerts
from app.analytics.clustering import ClusteringParams, st_dbscan, summarize_clusters, to_epoch_seconds
from app.analytics.intelligence import ENGINE_VERSION, ClusterEvidence, assess
from app.analytics.persistence import classify_persistence, coverage_days, detection_history
from app.analytics.proximity import compute_proximity
from app.config import Settings, get_settings
from app.core.audit import record_event
from app.db.engine import connection, transaction
from app.db.runs import finish_run, start_run
from app.ingestion.landcover.service import enrich_clusters

log = logging.getLogger(__name__)

CHUNK = 2000


def _load_window(settings: Settings) -> pd.DataFrame:
    since = datetime.now(timezone.utc) - timedelta(days=settings.cluster_window_days)
    with connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, latitude, longitude, acquired_at, acq_date, frp, brightness,
                       confidence_level, confidence_pct, daynight, instrument, product, cluster_id
                  FROM thermal_observations
                 WHERE acquired_at >= :since
                 ORDER BY acquired_at
                """
            ),
            {"since": since},
        ).mappings().all()
    frame = pd.DataFrame([dict(r) for r in rows])
    if not frame.empty:
        frame["acquired_at"] = pd.to_datetime(frame["acquired_at"], utc=True)
    return frame


def _assign_ids(summaries: list[dict], frame: pd.DataFrame) -> tuple[list[int], dict[int, int]]:
    """Give each new cluster the id of the previous cluster contributing most of its detections.

    Larger clusters choose first. Returns (indexes of summaries needing a fresh id,
    {superseded old cluster id: index of the summary that absorbed most of it}).
    """
    previous = dict(zip(frame["id"].astype("int64"), frame["cluster_id"]))
    claimed: set[int] = set()
    contributions: dict[int, dict[int, int]] = {}  # old id -> {summary index: count}
    for s in sorted(range(len(summaries)), key=lambda i: -summaries[i]["observation_count"]):
        summary = summaries[s]
        counts: dict[int, int] = {}
        for oid in summary["member_ids"]:
            old = previous.get(oid)
            if old is not None and not pd.isna(old):
                old = int(old)
                counts[old] = counts.get(old, 0) + 1
                contributions.setdefault(old, {})
                contributions[old][s] = contributions[old].get(s, 0) + 1
        chosen = next((cid for cid, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if cid not in claimed), None)
        if chosen is not None:
            claimed.add(chosen)
            summary["id"] = chosen
    merged: dict[int, int] = {}
    for old, per_summary in contributions.items():
        if old in claimed:
            continue
        target = max(per_summary.items(), key=lambda kv: kv[1])[0]
        merged[old] = target  # summary index; resolved to id after allocation
    return [i for i, s in enumerate(summaries) if "id" not in s], merged


def _upsert_clusters(conn, summaries: list[dict]) -> None:
    sql = text(
        """
        INSERT INTO thermal_clusters (
            id, status, merged_into_id, center_latitude, center_longitude, geom, hull, extent_radius_m,
            observation_count, max_frp, avg_frp, total_frp, max_brightness, start_time, end_time,
            duration_hours, detection_days, night_fraction, mean_confidence, instruments, products
        )
        SELECT u.id, 'active', NULL, u.lat, u.lon, ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326)::geography,
               CASE WHEN u.hull IS NULL THEN NULL ELSE ST_GeogFromText(u.hull) END,
               u.extent, u.n, u.max_frp, u.avg_frp, u.total_frp, u.max_b, u.t0, u.t1, u.dur, u.days,
               u.night, u.conf, string_to_array(u.instr, ','), string_to_array(u.prod, ',')
          FROM unnest(
                CAST(:id AS bigint[]), CAST(:lat AS float8[]), CAST(:lon AS float8[]), CAST(:hull AS text[]),
                CAST(:extent AS float8[]), CAST(:n AS int[]), CAST(:max_frp AS float8[]), CAST(:avg_frp AS float8[]),
                CAST(:total_frp AS float8[]), CAST(:max_b AS float8[]), CAST(:t0 AS timestamptz[]),
                CAST(:t1 AS timestamptz[]), CAST(:dur AS float8[]), CAST(:days AS int[]), CAST(:night AS float8[]),
                CAST(:conf AS float8[]), CAST(:instr AS text[]), CAST(:prod AS text[])
               ) AS u(id, lat, lon, hull, extent, n, max_frp, avg_frp, total_frp, max_b, t0, t1, dur, days,
                      night, conf, instr, prod)
        ON CONFLICT (id) DO UPDATE SET
            status = 'active', merged_into_id = NULL,
            center_latitude = EXCLUDED.center_latitude, center_longitude = EXCLUDED.center_longitude,
            geom = EXCLUDED.geom, hull = EXCLUDED.hull, extent_radius_m = EXCLUDED.extent_radius_m,
            observation_count = EXCLUDED.observation_count, max_frp = EXCLUDED.max_frp,
            avg_frp = EXCLUDED.avg_frp, total_frp = EXCLUDED.total_frp, max_brightness = EXCLUDED.max_brightness,
            start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time,
            duration_hours = EXCLUDED.duration_hours, detection_days = EXCLUDED.detection_days,
            night_fraction = EXCLUDED.night_fraction, mean_confidence = EXCLUDED.mean_confidence,
            instruments = EXCLUDED.instruments, products = EXCLUDED.products,
            land_cover_id = CASE
                WHEN abs(thermal_clusters.center_latitude - EXCLUDED.center_latitude) > 0.001
                  OR abs(thermal_clusters.center_longitude - EXCLUDED.center_longitude) > 0.001
                THEN NULL ELSE thermal_clusters.land_cover_id END
        """
    )
    for start in range(0, len(summaries), CHUNK):
        chunk = summaries[start : start + CHUNK]
        conn.execute(
            sql,
            {
                "id": [s["id"] for s in chunk],
                "lat": [s["center_latitude"] for s in chunk],
                "lon": [s["center_longitude"] for s in chunk],
                "hull": [s["hull_wkt"] for s in chunk],
                "extent": [s["extent_radius_m"] for s in chunk],
                "n": [s["observation_count"] for s in chunk],
                "max_frp": [s["max_frp"] for s in chunk],
                "avg_frp": [s["avg_frp"] for s in chunk],
                "total_frp": [s["total_frp"] for s in chunk],
                "max_b": [s["max_brightness"] for s in chunk],
                "t0": [s["start_time"] for s in chunk],
                "t1": [s["end_time"] for s in chunk],
                "dur": [s["duration_hours"] for s in chunk],
                "days": [s["detection_days"] for s in chunk],
                "night": [s["night_fraction"] for s in chunk],
                "conf": [s["mean_confidence"] for s in chunk],
                "instr": [",".join(s["instruments"]) for s in chunk],
                "prod": [",".join(s["products"]) for s in chunk],
            },
        )


def cluster_observations(settings: Settings) -> dict:
    frame = _load_window(settings)
    if frame.empty:
        with transaction() as conn:
            deactivated = conn.execute(
                text("UPDATE thermal_clusters SET status = 'inactive' WHERE status = 'active'")
            ).rowcount
        return {"observations": 0, "clusters": 0, "cluster_ids": [], "new": 0, "merged": 0, "deactivated": deactivated}

    params = ClusteringParams(settings.cluster_eps_km, settings.cluster_max_gap_hours, settings.cluster_min_samples)
    t_seconds = to_epoch_seconds(frame["acquired_at"])
    labels = st_dbscan(frame["latitude"].to_numpy(), frame["longitude"].to_numpy(), t_seconds, params)
    summaries = summarize_clusters(frame, labels)
    unassigned, merged = _assign_ids(summaries, frame)

    with transaction() as conn:
        if unassigned:
            new_ids = conn.execute(
                text(
                    "SELECT nextval(pg_get_serial_sequence('thermal_clusters', 'id')) FROM generate_series(1, :n)"
                ),
                {"n": len(unassigned)},
            ).scalars().all()
            for idx, new_id in zip(unassigned, new_ids):
                summaries[idx]["id"] = int(new_id)
        _upsert_clusters(conn, summaries)

        obs_ids, cluster_ids = [], []
        for s in summaries:
            obs_ids.extend(s["member_ids"])
            cluster_ids.extend([s["id"]] * len(s["member_ids"]))
        for start in range(0, len(obs_ids), 20000):
            conn.execute(
                text(
                    """
                    UPDATE thermal_observations o SET cluster_id = u.cid
                      FROM unnest(CAST(:oids AS bigint[]), CAST(:cids AS bigint[])) AS u(oid, cid)
                     WHERE o.id = u.oid AND o.cluster_id IS DISTINCT FROM u.cid
                    """
                ),
                {"oids": obs_ids[start : start + 20000], "cids": cluster_ids[start : start + 20000]},
            )

        if merged:
            old_ids = list(merged)
            targets = [summaries[i]["id"] for i in merged.values()]
            conn.execute(
                text(
                    """
                    UPDATE thermal_clusters c SET status = 'merged', merged_into_id = u.target
                      FROM unnest(CAST(:old AS bigint[]), CAST(:tgt AS bigint[])) AS u(old, target)
                     WHERE c.id = u.old
                    """
                ),
                {"old": old_ids, "tgt": targets},
            )
            conn.execute(
                text(
                    """
                    UPDATE incidents SET status = 'closed', closed_at = now(),
                           summary = coalesce(summary, '') || ' [Cluster merged into a larger event.]'
                     WHERE cluster_id = ANY(CAST(:old AS bigint[])) AND status <> 'closed'
                    """
                ),
                {"old": old_ids},
            )
        current = [s["id"] for s in summaries]
        deactivated = conn.execute(
            text(
                "UPDATE thermal_clusters SET status = 'inactive' "
                "WHERE status = 'active' AND NOT (id = ANY(CAST(:ids AS bigint[])))"
            ),
            {"ids": current},
        ).rowcount

    return {
        "observations": int(len(frame)),
        "clusters": len(summaries),
        "multi_observation_clusters": sum(1 for s in summaries if s["observation_count"] > 1),
        "cluster_ids": current,
        "new": len(unassigned),
        "merged": len(merged),
        "deactivated": deactivated,
        "params": params.__dict__,
    }


def _apply_persistence(cluster_ids: list[int], settings: Settings) -> dict:
    with transaction() as conn:
        coverage = coverage_days(conn, settings.persistence_lookback_days)
        history = detection_history(conn, cluster_ids, settings.persistence_radius_m, settings.persistence_lookback_days)
        ids, cats, det, cov, ratio, details = [], [], [], [], [], []
        counts: dict[str, int] = {}
        for cid in cluster_ids:
            h = history.get(cid, {})
            result = classify_persistence(
                h.get("detection_days", 1) or 1,
                coverage,
                radius_m=settings.persistence_radius_m,
                min_days_persistent=settings.persistence_min_days_persistent,
                min_coverage_days=settings.persistence_min_coverage_days,
                min_ratio=settings.persistence_min_ratio,
            )
            counts[result.category] = counts.get(result.category, 0) + 1
            ids.append(cid)
            cats.append(result.category)
            det.append(result.detection_days)
            cov.append(result.coverage_days)
            ratio.append(round(result.ratio, 4))
            details.append(
                json.dumps(
                    {
                        "explanation": result.explanation,
                        "radius_m": settings.persistence_radius_m,
                        "lookback_days": settings.persistence_lookback_days,
                        "observations_nearby": h.get("observations"),
                        "first_seen": h.get("first_seen"),
                        "last_seen": h.get("last_seen"),
                    },
                    default=str,
                )
            )
        for start in range(0, len(ids), CHUNK):
            sl = slice(start, start + CHUNK)
            conn.execute(
                text(
                    """
                    UPDATE thermal_clusters c
                       SET persistence_category = u.cat, persistence_detection_days = u.det,
                           persistence_coverage_days = u.cov, persistence_ratio = u.ratio,
                           persistence_details = CAST(u.details AS jsonb)
                      FROM unnest(CAST(:ids AS bigint[]), CAST(:cats AS text[]), CAST(:det AS int[]),
                                  CAST(:cov AS int[]), CAST(:ratio AS float8[]), CAST(:details AS text[]))
                           AS u(id, cat, det, cov, ratio, details)
                     WHERE c.id = u.id
                    """
                ),
                {"ids": ids[sl], "cats": cats[sl], "det": det[sl], "cov": cov[sl], "ratio": ratio[sl], "details": details[sl]},
            )
    return {"coverage_days": coverage, "categories": counts}


def _apply_intelligence(cluster_ids: list[int]) -> dict:
    with connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.id, c.observation_count, c.max_frp, c.avg_frp, c.night_fraction, c.mean_confidence,
                       c.detection_days, c.persistence_category, c.persistence_detection_days,
                       c.persistence_coverage_days, c.persistence_ratio, c.max_brightness, c.extent_radius_m,
                       (c.persistence_details ->> 'observations_nearby')::int AS observations_nearby,
                       c.persistence_details ->> 'explanation' AS persistence_explanation,
                       c.spatial_relationship, c.nearest_facility_distance_m, c.facility_member_share,
                       f.facility_type, f.name AS facility_name, f.source_ref AS facility_ref,
                       lc.status AS lc_status, lc.class_fractions, lc.dominant_class_name
                  FROM thermal_clusters c
                  LEFT JOIN industrial_facilities f ON f.id = c.nearest_facility_id
                  LEFT JOIN land_cover lc ON lc.id = c.land_cover_id
                 WHERE c.id = ANY(CAST(:ids AS bigint[]))
                """
            ),
            {"ids": cluster_ids},
        ).mappings().all()

    updates = []
    classes: dict[str, int] = {}
    for r in rows:
        assessment = assess(
            ClusterEvidence(
                observation_count=r["observation_count"],
                max_frp=r["max_frp"],
                avg_frp=r["avg_frp"],
                night_fraction=r["night_fraction"],
                mean_confidence=r["mean_confidence"],
                detection_days=r["detection_days"] or 1,
                persistence_category=r["persistence_category"],
                persistence_detection_days=r["persistence_detection_days"],
                persistence_coverage_days=r["persistence_coverage_days"],
                persistence_ratio=r["persistence_ratio"],
                persistence_explanation=r["persistence_explanation"],
                spatial_relationship=r["spatial_relationship"],
                facility_distance_m=r["nearest_facility_distance_m"],
                facility_type=r["facility_type"],
                facility_name=r["facility_name"],
                facility_ref=r["facility_ref"],
                facility_member_share=r["facility_member_share"],
                land_cover_status=r["lc_status"],
                land_cover_fractions=r["class_fractions"] or {},
                land_cover_dominant=r["dominant_class_name"],
                max_brightness=r["max_brightness"],
                extent_radius_m=r["extent_radius_m"],
                observations_nearby=r["observations_nearby"],
            )
        )
        key = assessment.classification_key
        classes[key] = classes.get(key, 0) + 1
        updates.append((r["id"], assessment))

    with transaction() as conn:
        for start in range(0, len(updates), CHUNK):
            chunk = updates[start : start + CHUNK]
            conn.execute(
                text(
                    """
                    UPDATE thermal_clusters c
                       SET classification = u.cls, evidence_strength = u.strength, risk_score = u.score,
                           priority = u.priority, intelligence = CAST(u.intel AS jsonb),
                           analysis_version = :ver, analyzed_at = now()
                      FROM unnest(CAST(:ids AS bigint[]), CAST(:cls AS text[]), CAST(:strength AS text[]),
                                  CAST(:score AS float8[]), CAST(:priority AS text[]), CAST(:intel AS text[]))
                           AS u(id, cls, strength, score, priority, intel)
                     WHERE c.id = u.id
                    """
                ),
                {
                    "ver": ENGINE_VERSION,
                    "ids": [cid for cid, _ in chunk],
                    "cls": [a.classification_key for _, a in chunk],
                    "strength": [a.evidence_strength for _, a in chunk],
                    "score": [a.risk_score for _, a in chunk],
                    "priority": [a.priority for _, a in chunk],
                    "intel": [json.dumps(a.as_dict()) for _, a in chunk],
                },
            )
    return {"assessed": len(updates), "classifications": classes}


def run_analysis(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    run_id = start_run("analysis", None, {"engine": ENGINE_VERSION})
    started = time.perf_counter()
    steps: dict[str, dict] = {}
    try:
        steps["clustering"] = cluster_observations(settings)
        ids = steps["clustering"].pop("cluster_ids")
        with transaction() as conn:
            steps["proximity"] = compute_proximity(conn, ids, settings)
        steps["persistence"] = _apply_persistence(ids, settings)
        try:
            steps["land_cover"] = enrich_clusters(ids, settings)
        except Exception as exc:  # land cover is contextual; its failure must not block analysis
            log.exception("land cover enrichment failed")
            steps["land_cover"] = {"status": "failed", "error": str(exc)[:300]}
        steps["intelligence"] = _apply_intelligence(ids)
        try:
            steps["incidents"] = update_incidents_and_alerts(ids, settings)
        except Exception as exc:
            from app.core.observability import record_failure

            record_failure("alerts", f"incident/alert update failed: {exc}")
            raise
    except Exception as exc:
        finish_run(run_id, "failed", details=steps, error=str(exc))
        record_event("analysis.failed", f"Analysis failed: {exc}", severity="error", source="analytics")
        raise

    elapsed = round(time.perf_counter() - started, 1)
    finish_run(
        run_id,
        "success",
        fetched=steps["clustering"]["observations"],
        valid=steps["clustering"]["clusters"],
        details={**steps, "elapsed_s": elapsed},
    )
    summary = {"run_id": run_id, "elapsed_s": elapsed, **steps}
    record_event(
        "analysis.completed",
        (
            f"Analysis complete: {steps['clustering']['clusters']} clusters from "
            f"{steps['clustering']['observations']} detections, {steps['proximity']['associated']} industrial-associated, "
            f"{steps['incidents'].get('new_incidents', 0)} new incidents"
        ),
        source="analytics",
        details={"run_id": run_id, "elapsed_s": elapsed, "incidents": steps["incidents"]},
    )
    return summary
