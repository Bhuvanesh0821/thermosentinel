"""NASA FIRMS HTTP client.

Two real-data access modes:

* ``api``          - Area API with a MAP_KEY: /api/area/csv/{MAP_KEY}/{PRODUCT}/{W,S,E,N}/{DAYS}[/{DATE}]
                     Region-exact, supports historical backfill (up to 5 days per request).
* ``public_feed``  - Keyless public NRT CSV files published by FIRMS per continent-scale region
                     (24h / 48h / 7d). Used automatically when no MAP_KEY is configured; records are
                     clipped to the configured region after download.

The MAP_KEY is never logged: URLs are masked before logging and error messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import httpx

from app.config import Settings
from app.core.errors import UpstreamError
from app.geo.region import BBox
from app.ingestion.http import request_with_retries

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FirmsProduct:
    code: str
    instrument: str
    platform: str
    public_path: str  # relative to /data/active_fire/


PRODUCTS: dict[str, FirmsProduct] = {
    "VIIRS_SNPP_NRT": FirmsProduct(
        "VIIRS_SNPP_NRT", "VIIRS", "Suomi NPP", "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_{region}_{window}.csv"
    ),
    "VIIRS_NOAA20_NRT": FirmsProduct(
        "VIIRS_NOAA20_NRT", "VIIRS", "NOAA-20", "noaa-20-viirs-c2/csv/J1_VIIRS_C2_{region}_{window}.csv"
    ),
    "VIIRS_NOAA21_NRT": FirmsProduct(
        "VIIRS_NOAA21_NRT", "VIIRS", "NOAA-21", "noaa-21-viirs-c2/csv/J2_VIIRS_C2_{region}_{window}.csv"
    ),
    "MODIS_NRT": FirmsProduct("MODIS_NRT", "MODIS", "Terra/Aqua", "modis-c6.1/csv/MODIS_C6_1_{region}_{window}.csv"),
}


class FirmsError(UpstreamError):
    code = "firms_error"


@dataclass
class FirmsFetch:
    product: str
    mode: str
    csv_text: str
    request_label: str  # masked, safe to log/store


class FirmsClient:
    def __init__(self, settings: Settings, http: httpx.Client):
        self.settings = settings
        self.http = http

    @property
    def mode(self) -> str:
        return self.settings.firms_mode

    def _mask(self, url: str) -> str:
        key = self.settings.firms_map_key
        return url.replace(key, "***MAP_KEY***") if key else url

    @staticmethod
    def _check_csv(text: str, label: str) -> str:
        stripped = text.lstrip("﻿").strip()
        if not stripped:
            raise FirmsError(f"FIRMS returned an empty body for {label}")
        first_line = stripped.splitlines()[0].lower()
        if not first_line.startswith("latitude"):
            # FIRMS reports API errors (bad key, bad area, quota) as plain text with HTTP 200.
            raise FirmsError(f"FIRMS error for {label}: {stripped[:200]}")
        return stripped

    def fetch_area(self, product: str, bbox: BBox, day_range: int, start_date: date | None = None) -> FirmsFetch:
        key = self.settings.firms_map_key
        if not key:
            raise FirmsError("NASA_FIRMS_MAP_KEY is not configured")
        if not 1 <= day_range <= 5:
            raise ValueError("FIRMS area API day_range must be between 1 and 5")
        url = f"{self.settings.firms_base_url}/api/area/csv/{key}/{product}/{bbox.as_firms()}/{day_range}"
        if start_date:
            url += f"/{start_date.isoformat()}"
        label = self._mask(url)
        response = request_with_retries(self.http, "GET", url, log_url=label)
        if response.status_code != 200:
            raise FirmsError(f"FIRMS API HTTP {response.status_code} for {label}: {response.text[:200]}")
        return FirmsFetch(product, "api", self._check_csv(response.text, label), label)

    def fetch_public_feed(self, product: str) -> FirmsFetch:
        spec = PRODUCTS[product]
        path = spec.public_path.format(
            region=self.settings.firms_public_feed_region, window=self.settings.firms_public_feed_window
        )
        url = f"{self.settings.firms_base_url}/data/active_fire/{path}"
        response = request_with_retries(self.http, "GET", url)
        if response.status_code != 200:
            raise FirmsError(f"FIRMS public feed HTTP {response.status_code} for {url}")
        return FirmsFetch(product, "public_feed", self._check_csv(response.text, url), url)

    def map_key_status(self) -> dict | None:
        """Transaction quota for the configured MAP_KEY (None when no key)."""
        key = self.settings.firms_map_key
        if not key:
            return None
        url = f"{self.settings.firms_base_url}/mapserver/mapkey_status/?MAP_KEY={key}"
        response = request_with_retries(self.http, "GET", url, attempts=2, log_url=self._mask(url))
        if response.status_code != 200:
            raise FirmsError(f"FIRMS MAP_KEY status HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise FirmsError(f"FIRMS MAP_KEY status returned non-JSON: {response.text[:120]}") from exc
