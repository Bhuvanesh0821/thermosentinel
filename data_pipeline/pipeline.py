"""ThermoSentinel data pipeline CLI.

Run from the repository root with the backend virtualenv:

    backend/.venv/Scripts/python data_pipeline/pipeline.py <command>      (Windows)
    backend/.venv/bin/python     data_pipeline/pipeline.py <command>      (Linux/macOS)

Commands
    check-sources   Live check of every external source (no database needed)
    migrate         Apply SQL migrations, register data sources, load the India boundary
    facilities      Ingest industrial facilities from OpenStreetMap (Overpass)
    firms           Ingest NASA FIRMS detections  [--backfill-days N]  (API mode only)
    analyze         Cluster, proximity, persistence, land cover, scoring, incidents/alerts
    run             Full pipeline: FIRMS -> facilities (when due) -> analysis
    retention       Delete detections older than OBSERVATION_RETENTION_DAYS
    status          Row counts and latest runs from the database
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import _bootstrap  # noqa: F401


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_check_sources(_args) -> int:
    from app.config import get_settings
    from app.geo.boundary import get_monitoring_area
    from app.geo.region import BBox
    from app.ingestion.facilities.overpass import OverpassClient
    from app.ingestion.facilities.service import element_to_record
    from app.ingestion.firms.client import FirmsClient
    from app.ingestion.firms.parser import parse_firms_csv
    from app.ingestion.http import build_client
    from app.ingestion.landcover.worldcover import WorldCoverSampler

    settings = get_settings()
    area = get_monitoring_area()
    ok = True
    print(f"Region: {settings.region_name} (official boundary + EEZ), fetch bbox {settings.bbox.as_list()}")
    with build_client(timeout=180) as http:
        firms = FirmsClient(settings, http)
        print(f"\nNASA FIRMS ({'Area API with MAP_KEY' if settings.firms_mode == 'api' else 'public NRT feed, no MAP_KEY'})")
        for product in settings.firms_product_list:
            t = time.perf_counter()
            try:
                fetch = firms.fetch_area(product, settings.bbox, 1) if settings.firms_mode == "api" else firms.fetch_public_feed(product)
                r = parse_firms_csv(fetch.csv_text, product, region=area)
                print(f"  OK   {product:17s} {len(r.observations):6d} inside India, {r.out_of_region:6d} outside discarded, {r.rejected} rejected ({time.perf_counter() - t:.1f}s)")
            except Exception as exc:
                ok = False
                print(f"  FAIL {product:17s} {exc}")

        print("\nOpenStreetMap / Overpass (Jamnagar test tile)")
        t = time.perf_counter()
        try:
            res = OverpassClient(settings.overpass_url_list, http, 120).fetch(BBox(69.5, 22.0, 70.5, 22.8))
            recs = [x for x in map(element_to_record, res.elements) if x]
            print(f"  OK   {len(recs)} facilities via {res.endpoint} (OSM snapshot {res.osm_base_timestamp}, {time.perf_counter() - t:.0f}s)")
        except Exception as exc:
            ok = False
            print(f"  FAIL {exc}")

    print("\nESA WorldCover (Jamnagar refinery sample)")
    t = time.perf_counter()
    sample = WorldCoverSampler(settings.landcover_worldcover_base_url, settings.landcover_target_resolution_m, settings.http_user_agent).sample(22.3368, 69.8666, 250)
    if sample.status == "ok":
        print(f"  OK   dominant {sample.dominant_name} {sample.dominant_fraction:.0%} (tile {sample.tile}, {time.perf_counter() - t:.1f}s)")
    else:
        ok = False
        print(f"  FAIL {sample.status}: {sample.error}")

    from app.db.engine import db_configured, ping

    print("\nNeon PostgreSQL")
    if not db_configured():
        ok = False
        print("  NOT CONFIGURED - set DATABASE_URL in thermosentinel/.env")
    else:
        try:
            info = ping()
            print(f"  OK   PostgreSQL {info['server_version']}, PostGIS {info['postgis_version'] or 'not installed yet (run migrate)'}, {info['latency_ms']} ms")
        except Exception as exc:
            ok = False
            print(f"  FAIL {exc.__class__.__name__}: {str(exc)[:200]}")
    return 0 if ok else 1


def cmd_migrate(_args) -> int:
    from app.db.migrate import apply_migrations
    from app.geo.region_sync import sync_monitoring_region
    from app.jobs import ensure_data_source_registry

    _print(apply_migrations())
    ensure_data_source_registry()
    _print({"monitoring_region": sync_monitoring_region()})
    return 0


def cmd_facilities(args) -> int:
    from app.config import get_settings
    from app.db.locks import job_lease
    from app.ingestion.facilities.service import ingest_facilities

    # Incremental by default: only tiles never loaded, failed, or older than FACILITIES_REFRESH_HOURS.
    from app.db.runs import close_orphaned_runs

    with job_lease("pipeline"):
        close_orphaned_runs()
        _print(ingest_facilities(get_settings(), force=args.force))
    return 0


def cmd_firms(args) -> int:
    from app.jobs import run_full_pipeline

    _print(
        run_full_pipeline(
            include_facilities=False, include_firms=True, include_analysis=False, backfill_days=args.backfill_days, trigger="cli"
        )
    )
    return 0


def cmd_analyze(_args) -> int:
    from app.jobs import run_full_pipeline

    _print(run_full_pipeline(include_facilities=False, include_firms=False, include_analysis=True, trigger="cli"))
    return 0


def cmd_run(args) -> int:
    from app.jobs import run_full_pipeline

    include = True if args.facilities else (False if args.no_facilities else None)
    _print(run_full_pipeline(include_facilities=include, backfill_days=args.backfill_days, trigger="cli"))
    return 0


def cmd_retention(_args) -> int:
    from app.jobs import apply_retention

    _print(apply_retention())
    return 0


def cmd_status(_args) -> int:
    from sqlalchemy import text

    from app.db.engine import connection

    with connection() as conn:
        counts = {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in (
                "thermal_observations",
                "industrial_facilities",
                "land_cover",
                "thermal_clusters",
                "incidents",
                "alerts",
                "notifications",
                "system_events",
            )
        }
        runs = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT DISTINCT ON (job) job, status, started_at, finished_at, records_valid, records_inserted, error "
                    "FROM ingestion_runs ORDER BY job, started_at DESC"
                )
            ).mappings()
        ]
    _print({"counts": counts, "latest_runs": runs})
    return 0


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.logging_config import configure_logging

    parser = argparse.ArgumentParser(description="ThermoSentinel data pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-sources", help="live check of external sources (no DB needed)").set_defaults(func=cmd_check_sources)
    sub.add_parser("migrate", help="apply migrations + load India boundary").set_defaults(func=cmd_migrate)
    p = sub.add_parser("facilities", help="ingest OSM industrial facilities (incremental, resumable)")
    p.add_argument("--force", action="store_true", help="re-query every tile even if fresh")
    p.set_defaults(func=cmd_facilities)
    p = sub.add_parser("firms", help="ingest NASA FIRMS detections")
    p.add_argument("--backfill-days", type=int, default=None)
    p.set_defaults(func=cmd_firms)
    sub.add_parser("analyze", help="run clustering + intelligence").set_defaults(func=cmd_analyze)
    p = sub.add_parser("run", help="full pipeline")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--facilities", action="store_true", help="force facility refresh")
    g.add_argument("--no-facilities", action="store_true", help="skip facility refresh")
    p.add_argument("--backfill-days", type=int, default=None)
    p.set_defaults(func=cmd_run)
    sub.add_parser("retention", help="apply data retention").set_defaults(func=cmd_retention)
    sub.add_parser("status", help="database counts and latest runs").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, "text")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
