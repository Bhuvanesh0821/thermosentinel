"""Static registry of external data sources (provenance + licensing) and status updates.

The registry lives in code so /api/data-sources can still describe every source when the
database is unreachable. Runtime status (last success, errors, counts) lives in the
`data_sources` table and is written by the ingestion services.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.engine import transaction

DATA_SOURCES: list[dict] = [
    {
        "id": "nasa_firms",
        "name": "NASA FIRMS Active Fire",
        "category": "thermal",
        "provider": "NASA LANCE / Fire Information for Resource Management System",
        "url": "https://firms.modaps.eosdis.nasa.gov",
        "license": "NASA Earth science data - open use; attribution requested",
        "description": "Near-real-time VIIRS (375 m) and MODIS (1 km) active fire / thermal anomaly detections.",
    },
    {
        "id": "osm_overpass",
        "name": "OpenStreetMap Industrial Infrastructure",
        "category": "infrastructure",
        "provider": "OpenStreetMap contributors via the Overpass API",
        "url": "https://www.openstreetmap.org/copyright",
        "license": "ODbL 1.0 - (c) OpenStreetMap contributors",
        "description": "Combustion power plants, refineries, chemical, steel, smelting, cement, mining, LNG and gas-flare sites mapped in OSM.",
    },
    {
        "id": "esa_worldcover",
        "name": "ESA WorldCover 10 m (v200, 2021)",
        "category": "land_cover",
        "provider": "European Space Agency - WorldCover consortium",
        "url": "https://esa-worldcover.org",
        "license": "CC BY 4.0 - (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium",
        "description": "Global 10 m land-cover map sampled around each thermal cluster to provide land-use context.",
    },
    {
        "id": "ne_india_boundary",
        "name": "India boundary (official claim)",
        "category": "boundary",
        "provider": "Natural Earth - Admin 0 Countries, point of view: India (1:10m)",
        "url": "https://www.naturalearthdata.com/about/disputed-boundaries-policy/",
        "license": "Public domain",
        "description": "India's boundary as depicted by the Government of India (includes all of J&K, Ladakh and Arunachal Pradesh). Data outside India is discarded.",
    },
    {
        "id": "marineregions_eez",
        "name": "India Exclusive Economic Zone",
        "category": "boundary",
        "provider": "Flanders Marine Institute - Maritime Boundaries Geodatabase (Marine Regions)",
        "url": "https://www.marineregions.org",
        "license": "CC BY 4.0 - Flanders Marine Institute (2023), Maritime Boundaries Geodatabase v12",
        "description": "Mainland and Andaman & Nicobar EEZs, so offshore platforms and flares (e.g. Mumbai High) are monitored.",
    },
    {
        "id": "nasa_gibs",
        "name": "NASA GIBS VIIRS True Colour",
        "category": "imagery",
        "provider": "NASA EOSDIS Global Imagery Browse Services",
        "url": "https://nasa-gibs.github.io/gibs-api-docs/",
        "license": "NASA open data - attribution requested",
        "description": "Daily VIIRS SNPP corrected-reflectance true-colour imagery tiles (map overlay).",
    },
    {
        "id": "eox_s2cloudless",
        "name": "Sentinel-2 cloudless 2021",
        "category": "imagery",
        "provider": "EOX IT Services GmbH",
        "url": "https://s2maps.eu",
        "license": "CC BY-NC-SA 4.0 - Sentinel-2 cloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2021)",
        "description": "10 m cloud-free Sentinel-2 mosaic used as the high-resolution satellite basemap.",
    },
]

REGISTRY_BY_ID = {s["id"]: s for s in DATA_SOURCES}


def ensure_registry(conn: Connection) -> None:
    """Idempotently upsert registry metadata without touching runtime status columns."""
    for src in DATA_SOURCES:
        conn.execute(
            text(
                """
                INSERT INTO data_sources (id, name, category, provider, url, license, description)
                VALUES (:id, :name, :category, :provider, :url, :license, :description)
                ON CONFLICT (id) DO UPDATE
                   SET name = EXCLUDED.name, category = EXCLUDED.category, provider = EXCLUDED.provider,
                       url = EXCLUDED.url, license = EXCLUDED.license, description = EXCLUDED.description
                """
            ),
            src,
        )


def set_status(
    source_id: str,
    status: str,
    *,
    message: str | None = None,
    success: bool = False,
    error: str | None = None,
    record_count: int | None = None,
    config: dict | None = None,
) -> None:
    with transaction() as conn:
        conn.execute(
            text(
                """
                UPDATE data_sources
                   SET status = :status,
                       status_message = :message,
                       last_attempt_at = now(),
                       last_success_at = CASE WHEN :success THEN now() ELSE last_success_at END,
                       last_error_at = CASE WHEN CAST(:error AS text) IS NOT NULL THEN now() ELSE last_error_at END,
                       last_error = COALESCE(CAST(:error AS text), CASE WHEN :success THEN NULL ELSE last_error END),
                       last_record_count = COALESCE(CAST(:record_count AS integer), last_record_count),
                       config = CASE WHEN CAST(:config AS jsonb) IS NULL THEN config ELSE CAST(:config AS jsonb) END
                 WHERE id = :id
                """
            ),
            {
                "id": source_id,
                "status": status,
                "message": message,
                "success": success,
                "error": error[:2000] if error else None,
                "record_count": record_count,
                "config": json.dumps(config) if config is not None else None,
            },
        )
