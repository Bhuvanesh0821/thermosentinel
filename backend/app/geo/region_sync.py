"""Keep the database's monitoring region in sync with the boundary file and enforce it."""

from __future__ import annotations

import json
import logging

from shapely.geometry import mapping
from sqlalchemy import text

from app.core.audit import record_event
from app.db.engine import transaction
from app.geo.boundary import get_monitoring_area

log = logging.getLogger(__name__)


def sync_monitoring_region() -> dict:
    """Load the India boundary into PostGIS when it changed, then purge anything outside it."""
    area = get_monitoring_area()
    with transaction() as conn:
        current = conn.execute(
            text("SELECT checksum FROM monitoring_regions WHERE name = :n AND role = 'monitoring_area'"),
            {"n": area.name},
        ).scalar_one_or_none()
        if current == area.checksum:
            return {"changed": False}
        for role, geom in (("land", area.land), ("monitoring_area", area.area)):
            conn.execute(
                text(
                    """
                    INSERT INTO monitoring_regions (name, role, geom, properties, checksum)
                    VALUES (:n, :role, ST_Multi(ST_GeomFromGeoJSON(:gj))::geography, CAST(:props AS jsonb), :ck)
                    ON CONFLICT (name, role) DO UPDATE
                       SET geom = EXCLUDED.geom, properties = EXCLUDED.properties,
                           checksum = EXCLUDED.checksum, loaded_at = now()
                    """
                ),
                {
                    "n": area.name,
                    "role": role,
                    "gj": json.dumps(mapping(geom)),
                    "props": json.dumps(area.properties.get(role, {})),
                    "ck": area.checksum,
                },
            )
        enforced = enforce_monitoring_region(conn, area.name)
    record_event(
        "region.updated",
        f"Monitoring region '{area.name}' loaded (official-claim boundary + EEZ); records outside it removed",
        source="boundary",
        details=enforced,
    )
    log.info("monitoring region synchronised", extra=enforced)
    return {"changed": True, **enforced}


def enforce_monitoring_region(conn, name: str) -> dict:
    """Delete detections and deactivate facilities/clusters lying outside the region."""
    params = {"n": name}
    region = "(SELECT geom FROM monitoring_regions WHERE name = :n AND role = 'monitoring_area')"
    observations = conn.execute(
        text(f"DELETE FROM thermal_observations o WHERE NOT ST_Covers({region}, o.geom)"), params
    ).rowcount
    facilities = conn.execute(
        text(f"UPDATE industrial_facilities f SET is_active = false WHERE f.is_active AND NOT ST_Covers({region}, f.geom)"),
        params,
    ).rowcount
    clusters = conn.execute(
        text(f"UPDATE thermal_clusters c SET status = 'inactive' WHERE c.status = 'active' AND NOT ST_Covers({region}, c.geom)"),
        params,
    ).rowcount
    return {"observations_removed": observations or 0, "facilities_deactivated": facilities or 0, "clusters_deactivated": clusters or 0}
