from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter

from app.config import get_settings
from app.core.cache import cached_ok
from app.core.responses import ok
from app.geo.boundary import get_monitoring_area
from app.ingestion.facilities.classify import FACILITY_TYPES
from app.ingestion.landcover.worldcover import WORLDCOVER_CLASSES

router = APIRouter(tags=["Map layers"])


@lru_cache(maxsize=1)
def _boundary_display() -> dict:
    return get_monitoring_area().display_geojson()


@router.get("/map/config", summary="Map configuration")
def get_map_config():
    """Region, basemaps and legends for the GIS client (no secrets)."""
    settings = get_settings()
    area = get_monitoring_area()
    land = area.land.bounds
    lat, lon = settings.bbox.center
    gibs_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    return ok(
        {
            "region": {
                "name": settings.region_name,
                "bbox": area.bbox.as_list(),
                "land_bbox": [round(v, 3) for v in land],
                "center": [lon, lat],
                "boundary": {
                    "land": area.properties.get("land", {}).get("source"),
                    "monitoring_area": area.properties.get("monitoring_area", {}).get("source"),
                },
            },
            # Keyless colourful vector basemap (roads, water, parks, place names). Its own boundary layers
            # are hidden client-side so the only boundary drawn is India's official one (/api/map/boundary).
            # A raster basemap is shown as a hybrid: imagery under the vector roads and labels.
            "base_style_url": "https://tiles.openfreemap.org/styles/liberty",
            "basemaps": [
                {
                    "id": "satellite",
                    "label": "Satellite",
                    "tiles": ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg"],
                    "tile_size": 256,
                    "max_zoom": 17,
                    "attribution": "Sentinel-2 cloudless 2021 by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2021)",
                },
                {
                    "id": "map",
                    "label": "Map",
                    "tiles": None,
                    "attribution": "OpenFreeMap (c) OpenMapTiles, data (c) OpenStreetMap contributors",
                },
                {
                    "id": "viirs",
                    "label": f"VIIRS true colour ({gibs_date})",
                    "tiles": [
                        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/"
                        f"default/{gibs_date}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg"
                    ],
                    "tile_size": 256,
                    "max_zoom": 9,
                    "attribution": "NASA EOSDIS GIBS - VIIRS SNPP Corrected Reflectance",
                },
            ],
            "facility_types": FACILITY_TYPES,
            "land_cover_classes": [{"code": c, "name": n, "color": col} for c, (n, col) in WORLDCOVER_CLASSES.items()],
            "proximity": {
                "near_m": settings.proximity_near_m,
                "association_m": settings.proximity_assoc_m,
                "search_m": settings.proximity_search_radius_m,
            },
        }
    )


@router.get("/map/boundary", summary="India boundary, monitoring area and outside mask (GeoJSON)")
def get_boundary():
    """India's official-claim land boundary, the monitoring area (land + EEZ) outline and a mask
    covering everything outside it. Simplified (~400 m) for display; ingestion clipping uses the
    full-resolution polygon."""
    area = get_monitoring_area()
    meta = {
            "land_source": area.properties.get("land", {}).get("source"),
            "land_license": area.properties.get("land", {}).get("license"),
            "monitoring_area_source": area.properties.get("monitoring_area", {}).get("source"),
            "monitoring_area_license": area.properties.get("monitoring_area", {}).get("license"),
    }
    return cached_ok("boundary", {}, lambda: (_boundary_display(), meta), ttl_s=24 * 3600, versioned=False)
