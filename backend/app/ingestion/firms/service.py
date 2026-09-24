"""FIRMS ingestion orchestration: fetch -> validate -> clip to region -> store -> record provenance."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.config import Settings, get_settings
from app.core.audit import record_event
from app.db.engine import transaction
from app.db.runs import finish_run, start_run
from app.geo.boundary import get_monitoring_area
from app.health.registry import set_status
from app.ingestion.firms.client import FirmsClient, FirmsError
from app.ingestion.firms.parser import parse_firms_csv
from app.ingestion.firms.repository import insert_observations
from app.ingestion.http import build_client

log = logging.getLogger(__name__)


def _api_requests(settings: Settings, backfill_days: int | None) -> list[tuple[int, date | None]]:
    """(day_range, start_date) pairs. Backfill is split into <=5-day windows (API limit)."""
    days = backfill_days if backfill_days else 0
    if days <= settings.firms_day_range:
        return [(settings.firms_day_range, None)]
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    requests: list[tuple[int, date | None]] = []
    cursor = start
    while cursor <= today:
        span = min(5, (today - cursor).days + 1)
        requests.append((span, cursor))
        cursor += timedelta(days=span)
    return requests


def ingest_firms(
    settings: Settings | None = None,
    *,
    backfill_days: int | None = None,
    products: list[str] | None = None,
) -> dict:
    """Fetch real FIRMS detections for the configured region and store new ones."""
    settings = settings or get_settings()
    products = products or settings.firms_product_list
    mode = settings.firms_mode
    area = get_monitoring_area()  # exact India polygon (land + EEZ) used for clipping
    bbox = settings.bbox  # rectangular extent used only for the FIRMS area request
    params = {
        "mode": mode,
        "products": products,
        "region": settings.region_name,
        "clip": "India official boundary + EEZ",
        "bbox": bbox.as_list(),
        "backfill_days": backfill_days,
        "day_range": settings.firms_day_range if mode == "api" else None,
        "public_feed": (
            f"{settings.firms_public_feed_region}/{settings.firms_public_feed_window}" if mode == "public_feed" else None
        ),
    }
    run_id = start_run("firms_ingest", "nasa_firms", params)
    log.info("FIRMS ingestion started", extra={"run_id": run_id, "mode": mode})

    totals = {"fetched": 0, "valid": 0, "inserted": 0, "rejected": 0, "out_of_region": 0, "duplicates": 0}
    per_product: dict[str, dict] = {}
    failures: dict[str, str] = {}

    with build_client(timeout=120) as http:
        client = FirmsClient(settings, http)
        for product in products:
            stats = {"fetched": 0, "valid": 0, "inserted": 0, "rejected": 0, "out_of_region": 0, "requests": []}
            try:
                fetches = (
                    [client.fetch_area(product, bbox, span, start) for span, start in _api_requests(settings, backfill_days)]
                    if mode == "api"
                    else [client.fetch_public_feed(product)]
                )
                for fetch in fetches:
                    parsed = parse_firms_csv(fetch.csv_text, product, region=area)
                    stats["requests"].append(fetch.request_label)
                    stats["fetched"] += parsed.total_rows
                    stats["valid"] += len(parsed.observations)
                    stats["rejected"] += parsed.rejected
                    stats["out_of_region"] += parsed.out_of_region
                    totals["duplicates"] += parsed.duplicates_in_batch
                    if parsed.errors:
                        stats.setdefault("parse_errors", []).extend(parsed.errors[:5])
                    if parsed.observations:
                        with transaction() as conn:
                            stats["inserted"] += insert_observations(
                                conn, parsed.observations, mode=fetch.mode, run_id=run_id
                            )
            except (FirmsError, Exception) as exc:  # one product failing must not abort the others
                failures[product] = str(exc)[:500]
                log.error("FIRMS product ingestion failed", extra={"product": product, "error": str(exc)[:300]})
            per_product[product] = stats
            for key in ("fetched", "valid", "inserted", "rejected", "out_of_region"):
                totals[key] += stats[key]

    if failures and len(failures) == len(products):
        status = "failed"
    elif failures:
        status = "partial"
    else:
        status = "success"

    details = {"products": per_product, "failures": failures, **{k: totals[k] for k in ("out_of_region", "duplicates")}}
    finish_run(
        run_id,
        status,
        fetched=totals["fetched"],
        valid=totals["valid"],
        inserted=totals["inserted"],
        rejected=totals["rejected"],
        details=details,
        error="; ".join(f"{p}: {e}" for p, e in failures.items()) or None,
    )

    mode_label = "FIRMS Area API (MAP_KEY)" if mode == "api" else "FIRMS public NRT feed (no MAP_KEY)"
    if status == "failed":
        set_status(
            "nasa_firms",
            "unavailable",
            message=f"{mode_label}: all products failed",
            error="; ".join(f"{p}: {e}" for p, e in failures.items()),
        )
    else:
        set_status(
            "nasa_firms",
            "connected" if status == "success" else "degraded",
            message=(
                f"{mode_label}; {totals['valid']} detections inside India, {totals['inserted']} new, "
                f"{totals['out_of_region']} outside India discarded"
            ),
            success=True,
            record_count=totals["valid"],
            config={"mode": mode, "products": products, "map_key_configured": mode == "api"},
        )

    summary = {"run_id": run_id, "status": status, "mode": mode, **totals, "failures": failures}
    record_event(
        "ingestion.firms.completed" if status != "failed" else "ingestion.firms.failed",
        f"FIRMS ingestion {status}: {totals['inserted']} new of {totals['valid']} valid detections",
        severity={"success": "info", "partial": "warning", "failed": "error"}[status],
        source="nasa_firms",
        details=summary,
    )
    log.info("FIRMS ingestion finished", extra=summary)
    return summary
