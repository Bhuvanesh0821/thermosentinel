"""Land-cover context for thermal clusters (sample, cache by location, link to clusters)."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.config import Settings, get_settings
from app.db.engine import connection, transaction
from app.health.registry import set_status
from app.ingestion.landcover.worldcover import DATASET_VERSION, LandCoverSample, WorldCoverSampler

log = logging.getLogger(__name__)


def cell_key(lat: float, lon: float, radius_m: int) -> str:
    # 0.001 deg (~110 m) grid: clusters at effectively the same place share one sample.
    return f"{lat:.3f},{lon:.3f}@{radius_m}"


def _store(samples: list[LandCoverSample]) -> dict[str, int]:
    """Insert samples and return {cell_key: land_cover_id}."""
    if not samples:
        return {}
    ids: dict[str, int] = {}
    with transaction() as conn:
        for s in samples:
            key = cell_key(s.latitude, s.longitude, s.radius_m)
            row_id = conn.execute(
                text(
                    """
                    INSERT INTO land_cover (
                        source_id, dataset_version, cell_key, latitude, longitude, geom, sample_radius_m,
                        resolution_m, status, dominant_class_code, dominant_class_name, dominant_fraction,
                        class_fractions, source_tile, error
                    ) VALUES (
                        'esa_worldcover', :ver, :key, :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius,
                        :res, :status, :code, :name, :frac, CAST(:fractions AS jsonb), :tile, :error
                    )
                    ON CONFLICT (source_id, dataset_version, cell_key) DO UPDATE SET
                        status = EXCLUDED.status, resolution_m = EXCLUDED.resolution_m,
                        dominant_class_code = EXCLUDED.dominant_class_code,
                        dominant_class_name = EXCLUDED.dominant_class_name,
                        dominant_fraction = EXCLUDED.dominant_fraction,
                        class_fractions = EXCLUDED.class_fractions, error = EXCLUDED.error,
                        sampled_at = now()
                    RETURNING id
                    """
                ),
                {
                    "ver": DATASET_VERSION,
                    "key": key,
                    "lat": s.latitude,
                    "lon": s.longitude,
                    "radius": s.radius_m,
                    "res": s.resolution_m,
                    "status": s.status,
                    "code": s.dominant_code,
                    "name": s.dominant_name,
                    "frac": s.dominant_fraction,
                    "fractions": json.dumps(s.fractions),
                    "tile": s.tile,
                    "error": s.error,
                },
            ).scalar_one()
            ids[key] = row_id
    return ids


def enrich_clusters(cluster_ids: list[int], settings: Settings | None = None) -> dict:
    """Attach land-cover samples to clusters that lack one (bounded per run)."""
    settings = settings or get_settings()
    if not settings.landcover_enabled:
        set_status("esa_worldcover", "disabled", message="LANDCOVER_ENABLED=false")
        return {"status": "disabled"}
    if not cluster_ids:
        return {"status": "skipped", "sampled": 0}

    radius = settings.landcover_sample_radius_m
    with connection() as conn:
        pending = conn.execute(
            text(
                """
                SELECT id, center_latitude AS lat, center_longitude AS lon
                  FROM thermal_clusters
                 WHERE id = ANY(CAST(:ids AS bigint[])) AND land_cover_id IS NULL
                 ORDER BY industrial_association DESC, observation_count DESC, max_frp DESC NULLS LAST
                """
            ),
            {"ids": cluster_ids},
        ).mappings().all()
        keys = {r["id"]: cell_key(r["lat"], r["lon"], radius) for r in pending}
        existing = dict(
            conn.execute(
                text(
                    "SELECT cell_key, id FROM land_cover WHERE source_id = 'esa_worldcover' "
                    "AND dataset_version = :ver AND cell_key = ANY(CAST(:keys AS text[])) AND status <> 'error'"
                ),
                {"ver": DATASET_VERSION, "keys": list(set(keys.values()))},
            ).all()
        )

    reused = sum(1 for key in keys.values() if key in existing)
    to_sample: dict[str, tuple[float, float]] = {}
    for r in pending:
        key = keys[r["id"]]
        if key not in existing and key not in to_sample:
            to_sample[key] = (float(r["lat"]), float(r["lon"]))
    limit = settings.landcover_max_samples_per_run
    deferred = max(0, len(to_sample) - limit)
    batch = list(to_sample.values())[:limit]

    samples: list[LandCoverSample] = []
    if batch:
        sampler = WorldCoverSampler(
            settings.landcover_worldcover_base_url, settings.landcover_target_resolution_m, settings.http_user_agent
        )

        def work(point: tuple[float, float]) -> LandCoverSample:
            return sampler.sample(point[0], point[1], radius)

        with ThreadPoolExecutor(max_workers=settings.landcover_workers) as pool:
            samples = list(pool.map(work, batch))
    new_ids = _store(samples)
    existing.update(new_ids)

    with transaction() as conn:
        pairs = [(cid, existing[key]) for cid, key in keys.items() if key in existing]
        if pairs:
            conn.execute(
                text(
                    """
                    UPDATE thermal_clusters c SET land_cover_id = u.lc
                      FROM unnest(CAST(:cids AS bigint[]), CAST(:lcs AS bigint[])) AS u(cid, lc)
                     WHERE c.id = u.cid
                    """
                ),
                {"cids": [p[0] for p in pairs], "lcs": [p[1] for p in pairs]},
            )

    ok = sum(1 for s in samples if s.status == "ok")
    errors = [s.error for s in samples if s.status == "error"]
    no_data = sum(1 for s in samples if s.status == "no_data")
    summary = {
        "sampled": len(samples),
        "ok": ok,
        "no_data": no_data,
        "errors": len(errors),
        "clusters_linked_to_existing_samples": reused,
        "deferred_to_next_run": deferred,
    }
    if samples and ok == 0 and errors:
        set_status("esa_worldcover", "unavailable", message="WorldCover sampling failed", error=errors[0])
    elif samples:
        set_status(
            "esa_worldcover",
            "degraded" if errors else "connected",
            message=f"{ok} samples this run ({len(errors)} errors, {deferred} deferred)",
            success=ok > 0,
            record_count=ok,
            config={"dataset_version": DATASET_VERSION, "sample_radius_m": radius},
        )
    log.info("land cover enrichment finished", extra=summary)
    return summary
