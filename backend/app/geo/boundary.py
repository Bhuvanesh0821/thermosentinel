"""India monitoring area (official-claim land boundary + EEZ).

Loaded from database/boundaries/india_monitoring_area.geojson, built reproducibly by
data_pipeline/build_india_boundary.py. Every ingested record is clipped to this area, so no
data from outside India ever reaches the database, the map or the statistics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.geo.region import BBox

WORLD = box(-180.0, -85.0, 180.0, 85.0)


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    return MultiPolygon([p for g in polys for p in (g.geoms if isinstance(g, MultiPolygon) else [g])])


@dataclass
class MonitoringArea:
    name: str
    land: MultiPolygon
    area: MultiPolygon
    properties: dict = field(default_factory=dict)
    checksum: str = ""

    def __post_init__(self) -> None:
        shapely.prepare(self.area)
        shapely.prepare(self.land)
        west, south, east, north = self.area.bounds
        self.bbox = BBox(round(west, 3), round(south, 3), round(east, 3), round(north, 3))

    def contains(self, lat: float, lon: float) -> bool:
        return bool(shapely.intersects_xy(self.area, lon, lat))

    def contains_many(self, lats, lons) -> np.ndarray:
        return shapely.intersects_xy(self.area, np.asarray(lons, dtype=float), np.asarray(lats, dtype=float))

    def intersects_bbox(self, bbox: BBox) -> bool:
        return self.area.intersects(box(bbox.west, bbox.south, bbox.east, bbox.north))

    def display_geojson(self, tolerance: float = 0.004) -> dict:
        """Simplified land outline, monitoring-area outline and outside-mask for the map."""
        land = self.land.simplify(tolerance, preserve_topology=True)
        area = self.area.simplify(tolerance, preserve_topology=True)
        mask = WORLD.difference(area)
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"role": "mask"}, "geometry": mapping(mask)},
                {"type": "Feature", "properties": {"role": "monitoring_area"}, "geometry": mapping(area.boundary)},
                {"type": "Feature", "properties": {"role": "land"}, "geometry": mapping(land.boundary)},
            ],
        }


def load_monitoring_area(path: Path) -> MonitoringArea:
    raw = path.read_bytes()
    payload = json.loads(raw)
    by_role = {f["properties"]["role"]: f for f in payload["features"]}
    if "land" not in by_role or "monitoring_area" not in by_role:
        raise ValueError(f"{path} must contain 'land' and 'monitoring_area' features")
    return MonitoringArea(
        name=by_role["land"]["properties"].get("name", "India"),
        land=_as_multipolygon(shape(by_role["land"]["geometry"])),
        area=_as_multipolygon(shape(by_role["monitoring_area"]["geometry"])),
        properties={role: f["properties"] for role, f in by_role.items()},
        checksum=hashlib.sha256(raw).hexdigest(),
    )


@lru_cache
def get_monitoring_area() -> MonitoringArea:
    from app.config import get_settings

    return load_monitoring_area(get_settings().region_boundary_file)
