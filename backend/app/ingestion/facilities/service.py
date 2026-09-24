"""Industrial facility ingestion from OpenStreetMap (Overpass), tiled over the region."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid
from sqlalchemy import text

from app.config import Settings, get_settings
from app.core.audit import record_event
from app.core.events import bus
from app.db.engine import transaction
from app.db.runs import finish_run, start_run
from app.geo.boundary import get_monitoring_area
from app.geo.region import BBox
from app.health.registry import set_status
from app.ingestion.facilities.classify import classify_facility, is_thermally_relevant
from app.ingestion.facilities.overpass import OverpassClient, OverpassError
from app.ingestion.facilities.repository import FacilityRecord, upsert_facilities
from app.ingestion.http import build_client

log = logging.getLogger(__name__)

SIMPLIFY_TOLERANCE_DEG = 0.00005  # ~5 m; keeps footprints small for Neon free-tier storage


def element_to_record(element: dict) -> FacilityRecord | None:
    """Convert one Overpass element into a FacilityRecord (None if unusable)."""
    tags = element.get("tags") or {}
    if not tags or not is_thermally_relevant(tags):
        return None
    etype = element.get("type")
    footprint_wkt = None

    if etype == "node":
        lat, lon = element.get("lat"), element.get("lon")
    elif etype == "way":
        coords = [(p["lon"], p["lat"]) for p in element.get("geometry") or [] if p]
        if not coords:
            return None
        if len(coords) >= 4 and coords[0] == coords[-1]:
            shape = make_valid(Polygon(coords))
            if shape.geom_type == "GeometryCollection":  # keep polygonal parts only
                shape = unary_union([g for g in shape.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
            if not shape.is_empty and shape.area > 0:
                simplified = shape.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
                footprint_wkt = simplified.wkt
                centroid = shape.representative_point() if not shape.centroid.within(shape) else shape.centroid
            else:
                centroid = LineString(coords).centroid
        elif len(coords) >= 2:
            centroid = LineString(coords).centroid
        else:
            centroid = Point(coords[0])
        lat, lon = centroid.y, centroid.x
    elif etype == "relation":
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    else:
        return None

    if lat is None or lon is None:
        return None
    facility_type, subtype = classify_facility(tags)
    return FacilityRecord(
        source_ref=f"{etype}/{element['id']}",
        name=tags.get("name:en") or tags.get("name"),
        facility_type=facility_type,
        facility_subtype=subtype,
        operator=tags.get("operator"),
        website=tags.get("website") or tags.get("contact:website"),
        latitude=float(lat),
        longitude=float(lon),
        footprint_wkt=footprint_wkt,
        tags=tags,
    )


def _tile_key(tile: BBox) -> str:
    return tile.as_overpass()


def _due_tiles(tiles: list[BBox], refresh_hours: int, force: bool) -> list[BBox]:
    """Tiles never loaded, last failed, or older than the refresh interval."""
    if force:
        return tiles
    with transaction() as conn:
        fresh = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tile_key FROM facility_tiles WHERE status = 'success' "
                    "AND last_success_at >= now() - make_interval(hours => :h)"
                ),
                {"h": refresh_hours},
            )
        }
    return [t for t in tiles if _tile_key(t) not in fresh]


def _record_tile(tile: BBox, run_id: int, *, ok: bool, elements: int = 0, facilities: int = 0,
                 endpoint: str | None = None, osm_ts: str | None = None, error: str | None = None) -> None:
    with transaction() as conn:
        conn.execute(
            text(
                """
                INSERT INTO facility_tiles (tile_key, west, south, east, north, status, element_count, facility_count,
                                            endpoint, osm_base_timestamp, last_attempt_at, last_success_at, last_error,
                                            ingestion_run_id)
                VALUES (:k, :w, :s, :e, :n, :st, :el, :fc, :ep, CAST(:ts AS timestamptz), now(),
                        CASE WHEN :ok THEN now() END, :err, :run)
                ON CONFLICT (tile_key) DO UPDATE SET
                    status = EXCLUDED.status, element_count = EXCLUDED.element_count,
                    facility_count = EXCLUDED.facility_count, endpoint = EXCLUDED.endpoint,
                    osm_base_timestamp = COALESCE(EXCLUDED.osm_base_timestamp, facility_tiles.osm_base_timestamp),
                    last_attempt_at = now(),
                    last_success_at = COALESCE(EXCLUDED.last_success_at, facility_tiles.last_success_at),
                    last_error = EXCLUDED.last_error, ingestion_run_id = EXCLUDED.ingestion_run_id
                """
            ),
            {
                "k": _tile_key(tile), "w": tile.west, "s": tile.south, "e": tile.east, "n": tile.north,
                "st": "success" if ok else "failed", "el": elements, "fc": facilities, "ep": endpoint,
                "ts": osm_ts, "ok": ok, "err": (error or None) and error[:1000], "run": run_id,
            },
        )


def _deactivate_if_complete(tiles: list[BBox]) -> int:
    """When every region tile has a successful load, facilities not seen since the oldest tile
    refresh no longer exist in OSM and are marked inactive (never deleted)."""
    keys = [_tile_key(t) for t in tiles]
    with transaction() as conn:
        row = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE status = 'success') AS ok, min(last_success_at) AS oldest "
                "FROM facility_tiles WHERE tile_key = ANY(CAST(:keys AS text[]))"
            ),
            {"keys": keys},
        ).mappings().one()
        if row["ok"] != len(keys) or row["oldest"] is None:
            return 0
        return conn.execute(
            text(
                "UPDATE industrial_facilities SET is_active = false "
                "WHERE source_id = 'osm_overpass' AND is_active AND last_seen_at < :oldest"
            ),
            {"oldest": row["oldest"]},
        ).rowcount or 0


def ingest_facilities(settings: Settings | None = None, *, force: bool = False) -> dict:
    """Incremental, resumable facility refresh.

    Each Overpass tile is saved the moment it completes (so facilities appear on the map
    progressively and a later failure never loses finished tiles). Only tiles that were never
    loaded, failed last time, or are older than FACILITIES_REFRESH_HOURS are queried.
    """
    settings = settings or get_settings()
    area = get_monitoring_area()
    # Only query tiles that touch India; everything returned is clipped to the polygon again.
    region_tiles = [t for t in settings.bbox.tiles(settings.overpass_tile_deg) if area.intersects_bbox(t)]
    tiles = _due_tiles(region_tiles, settings.facilities_refresh_hours, force)
    run_id = start_run(
        "facilities_ingest",
        "osm_overpass",
        {
            "region": settings.region_name,
            "clip": "India official boundary + EEZ",
            "bbox": settings.bbox.as_list(),
            "region_tiles": len(region_tiles),
            "tiles_due": len(tiles),
            "force": force,
        },
    )
    log.info("facility ingestion started", extra={"run_id": run_id, "tiles_due": len(tiles), "region_tiles": len(region_tiles)})

    outside = fetched = inserted = updated = saved = 0
    failed_tiles: list[str] = []
    endpoints: set[str] = set()
    osm_timestamp: str | None = None
    by_type: dict[str, int] = {}
    started = time.perf_counter()

    lock = threading.Lock()
    done = 0

    def fetch(tile: BBox):
        t0 = time.perf_counter()
        with build_client(timeout=settings.overpass_timeout_s + 30) as http:
            client = OverpassClient(settings.overpass_url_list, http, settings.overpass_timeout_s)
            try:
                return tile, client.fetch(tile), None, time.perf_counter() - t0
            except OverpassError as exc:
                return tile, None, exc, time.perf_counter() - t0
            finally:
                time.sleep(1.0)  # be polite to the shared public Overpass infrastructure

    with ThreadPoolExecutor(max_workers=settings.overpass_concurrency) as pool:
        for tile, result, exc, took in (f.result() for f in as_completed([pool.submit(fetch, t) for t in tiles])):
            with lock:
                done += 1
                index = done
            if exc is not None:
                failed_tiles.append(_tile_key(tile))
                _record_tile(tile, run_id, ok=False, error=str(exc))
                log.error(
                    f"facility tile {index}/{len(tiles)} failed (will retry next run)",
                    extra={"tile": _tile_key(tile), "error": str(exc)[:300]},
                )
                continue
            endpoints.add(result.endpoint)
            osm_timestamp = osm_timestamp or result.osm_base_timestamp
            fetched += len(result.elements)
            records: dict[str, FacilityRecord] = {}
            for element in result.elements:
                record = element_to_record(element)
                if record is None:
                    continue
                if not area.contains(record.latitude, record.longitude):
                    outside += 1
                    continue
                records[record.source_ref] = record
            if records:
                with transaction() as conn:
                    ins, upd = upsert_facilities(
                        conn, list(records.values()), run_id=run_id, source_timestamp=result.osm_base_timestamp
                    )
                inserted += ins
                updated += upd
                saved += len(records)
                for r in records.values():
                    by_type[r.facility_type] = by_type.get(r.facility_type, 0) + 1
            _record_tile(
                tile, run_id, ok=True, elements=len(result.elements), facilities=len(records),
                endpoint=result.endpoint, osm_ts=result.osm_base_timestamp,
            )
            log.info(
                f"facility tile {index}/{len(tiles)} saved: {len(records)} facilities "
                f"({inserted} new so far) in {took:.0f}s via {result.endpoint}"
            )
            bus.publish(
                "ingestion.facilities.progress",
                {"tile": index, "of": len(tiles), "facilities_saved": saved, "new": inserted},
            )

    deactivated = _deactivate_if_complete(region_tiles)

    if tiles and len(failed_tiles) == len(tiles):
        status = "failed"
    elif failed_tiles:
        status = "partial"
    else:
        status = "success"

    with transaction() as conn:
        totals = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE status = 'success') AS ok, count(*) AS total FROM facility_tiles "
                "WHERE tile_key = ANY(CAST(:keys AS text[]))"
            ),
            {"keys": [_tile_key(t) for t in region_tiles]},
        ).mappings().one()
        active = conn.execute(text("SELECT count(*) FROM industrial_facilities WHERE is_active")).scalar_one()

    details = {
        "outside_india_discarded": outside,
        "failed_tiles": failed_tiles,
        "endpoints": sorted(endpoints),
        "osm_base_timestamp": osm_timestamp,
        "by_type": by_type,
        "deactivated": deactivated,
        "region_tiles_loaded": f"{totals['ok']}/{len(region_tiles)}",
        "elapsed_s": round(time.perf_counter() - started),
    }
    finish_run(
        run_id,
        status,
        fetched=fetched,
        valid=saved,
        inserted=inserted,
        updated=updated,
        details=details,
        error=f"{len(failed_tiles)} of {len(tiles)} tiles failed (will be retried next run)" if failed_tiles else None,
    )
    coverage = f"{totals['ok']}/{len(region_tiles)} India tiles loaded"
    if status == "failed" and totals["ok"] == 0:
        set_status(
            "osm_overpass",
            "unavailable",
            message="All Overpass tiles failed",
            error=f"All {len(tiles)} Overpass tile queries failed on every configured endpoint",
        )
    else:
        set_status(
            "osm_overpass",
            "connected" if totals["ok"] == len(region_tiles) else "degraded",
            message=f"{active} active facilities; {coverage}" + (f" (OSM snapshot {osm_timestamp})" if osm_timestamp else ""),
            success=status != "failed",
            record_count=int(active),
            config={"osm_base_timestamp": osm_timestamp, "endpoints": sorted(endpoints), "tiles_loaded": totals["ok"]},
        )

    summary = {
        "run_id": run_id,
        "status": status,
        "tiles_queried": len(tiles),
        "region_tiles_loaded": details["region_tiles_loaded"],
        "facilities": saved,
        "active_facilities": int(active),
        "inserted": inserted,
        "updated": updated,
        "deactivated": deactivated,
        "outside_india_discarded": outside,
        "failed_tiles": len(failed_tiles),
        "by_type": by_type,
    }
    record_event(
        "ingestion.facilities.completed" if status != "failed" else "ingestion.facilities.failed",
        f"Facility ingestion {status}: {saved} facilities saved ({inserted} new); {coverage}",
        severity={"success": "info", "partial": "warning", "failed": "error"}[status],
        source="osm_overpass",
        details=summary,
    )
    return summary
