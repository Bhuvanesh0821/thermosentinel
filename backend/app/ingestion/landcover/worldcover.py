"""ESA WorldCover 10 m (v200, 2021) adapter.

Reads the official Cloud-Optimised GeoTIFF tiles published on the AWS Open Data registry
(s3://esa-worldcover) with HTTP range requests - only the few internal blocks covering a
sample window are downloaded. Reads use the COG's internal overviews at roughly
`target_resolution_m`, which is ample for characterising the ~375 m footprint of a VIIRS
detection and ~10x faster than full-resolution reads.

Tiles are 3x3 degrees named by their south-west corner, e.g. N21E069.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

DATASET_VERSION = "v200 (2021)"

# Official WorldCover legend (code -> (name, colour)).
WORLDCOVER_CLASSES: dict[int, tuple[str, str]] = {
    10: ("Tree cover", "#006400"),
    20: ("Shrubland", "#FFBB22"),
    30: ("Grassland", "#FFFF4C"),
    40: ("Cropland", "#F096FF"),
    50: ("Built-up", "#FA0000"),
    60: ("Bare / sparse vegetation", "#B4B4B4"),
    70: ("Snow and ice", "#F0F0F0"),
    80: ("Permanent water bodies", "#0064C8"),
    90: ("Herbaceous wetland", "#0096A0"),
    95: ("Mangroves", "#00CF75"),
    100: ("Moss and lichen", "#FAE6A0"),
}

_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": 3,
    "GDAL_HTTP_RETRY_DELAY": 2,
    "GDAL_HTTP_TIMEOUT": 60,
    "VSI_CACHE": True,
    "GDAL_CACHEMAX": 256,  # MB; rasterio requires an int here
}


def tile_id(lat: float, lon: float) -> str:
    lat0 = int(math.floor(lat / 3.0) * 3)
    lon0 = int(math.floor(lon / 3.0) * 3)
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}"


@dataclass
class LandCoverSample:
    latitude: float
    longitude: float
    radius_m: int
    status: str  # ok | no_data | error
    tile: str
    resolution_m: float | None = None
    dominant_code: int | None = None
    dominant_name: str | None = None
    dominant_fraction: float | None = None
    fractions: dict[str, float] = field(default_factory=dict)  # class code (str) -> fraction
    error: str | None = None


class WorldCoverSampler:
    """Thread-safe sampler; each thread keeps its own open GDAL datasets."""

    def __init__(self, base_url: str, target_resolution_m: float = 40.0, user_agent: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.target_resolution_m = target_resolution_m
        self.user_agent = user_agent
        self._local = threading.local()
        self._missing_tiles: set[str] = set()

    def _url(self, tile: str) -> str:
        return f"/vsicurl/{self.base_url}/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"

    def _env(self):
        import rasterio

        env = dict(_GDAL_ENV)
        if self.user_agent:
            env["GDAL_HTTP_USERAGENT"] = self.user_agent
        return rasterio.Env(**env)

    def _dataset(self, tile: str):
        import rasterio

        cache = getattr(self._local, "datasets", None)
        if cache is None:
            cache = self._local.datasets = {}
        if tile not in cache:
            cache[tile] = rasterio.open(self._url(tile))
        return cache[tile]

    def close(self) -> None:
        for ds in getattr(self._local, "datasets", {}).values():
            ds.close()
        self._local.datasets = {}

    def sample(self, lat: float, lon: float, radius_m: int) -> LandCoverSample:
        from rasterio.enums import Resampling
        from rasterio.errors import RasterioIOError
        from rasterio.windows import from_bounds

        tile = tile_id(lat, lon)
        if tile in self._missing_tiles:
            return LandCoverSample(lat, lon, radius_m, "no_data", tile, error="no WorldCover tile (open ocean)")
        try:
            with self._env():
                ds = self._dataset(tile)
                dlat = radius_m / 111_320.0
                dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
                window = from_bounds(lon - dlon, lat - dlat, lon + dlon, lat + dlat, ds.transform)
                pixel_m = abs(ds.res[0]) * 111_320.0
                native_px = max(1.0, window.width)
                target_px = max(3, int(round(native_px * pixel_m / self.target_resolution_m)))
                out = min(int(native_px), target_px) or 1
                data = ds.read(1, window=window, out_shape=(out, out), resampling=Resampling.nearest, boundless=False)
                resolution = (2 * radius_m) / out
        except RasterioIOError as exc:
            msg = str(exc)
            if "404" in msg or "403" in msg or "does not exist" in msg.lower() or "not recognized" in msg.lower():
                self._missing_tiles.add(tile)
                return LandCoverSample(lat, lon, radius_m, "no_data", tile, error="no WorldCover tile (open ocean)")
            return LandCoverSample(lat, lon, radius_m, "error", tile, error=msg[:300])
        except Exception as exc:  # network hiccups etc.
            return LandCoverSample(lat, lon, radius_m, "error", tile, error=str(exc)[:300])

        values, counts = np.unique(data[data > 0], return_counts=True)
        total = int(counts.sum())
        if total == 0:
            return LandCoverSample(
                lat, lon, radius_m, "no_data", tile, resolution_m=resolution, error="no land-cover pixels (open sea / outside coverage)"
            )
        fractions = {str(int(v)): round(int(c) / total, 4) for v, c in zip(values, counts)}
        dom_code = int(values[int(np.argmax(counts))])
        return LandCoverSample(
            latitude=lat,
            longitude=lon,
            radius_m=radius_m,
            status="ok",
            tile=tile,
            resolution_m=round(resolution, 1),
            dominant_code=dom_code,
            dominant_name=WORLDCOVER_CLASSES.get(dom_code, (f"class {dom_code}", ""))[0],
            dominant_fraction=fractions[str(dom_code)],
            fractions=fractions,
        )
