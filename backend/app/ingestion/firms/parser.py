"""Parse and normalise FIRMS CSV (VIIRS and MODIS, API and public feed variants).

Column differences handled:
  VIIRS: bright_ti4 / bright_ti5, confidence in {l,n,h} (API) or {low,nominal,high} (feed)
  MODIS: brightness / bright_t31, confidence 0-100
  Public feed files omit the `instrument` column.

Every row is validated; invalid rows are counted and reported, never silently stored.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.ingestion.firms.client import PRODUCTS

log = logging.getLogger(__name__)

SATELLITE_NAMES = {
    "N": "Suomi NPP",
    "NPP": "Suomi NPP",
    "N20": "NOAA-20",
    "1": "NOAA-20",
    "J1": "NOAA-20",
    "N21": "NOAA-21",
    "2": "NOAA-21",
    "J2": "NOAA-21",
    "T": "Terra",
    "TERRA": "Terra",
    "A": "Aqua",
    "AQUA": "Aqua",
}

VIIRS_CONFIDENCE = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high"}


class FirmsObservation(BaseModel):
    """A validated, normalised FIRMS detection ready for storage."""

    source_record_key: str
    product: str
    instrument: str
    satellite: str | None
    satellite_name: str | None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    brightness: float | None = Field(default=None, gt=0, lt=1000)
    brightness_2: float | None = Field(default=None, gt=0, lt=1000)
    frp: float | None = Field(default=None, ge=0)
    scan: float | None = None
    track: float | None = None
    acq_date: str
    acq_time: str = Field(pattern=r"^\d{4}$")
    acquired_at: datetime
    confidence_raw: str | None
    confidence_level: str | None
    confidence_pct: int | None = Field(default=None, ge=0, le=100)
    daynight: str | None
    version: str | None

    @field_validator("daynight")
    @classmethod
    def _dn(cls, v):
        if v is not None and v not in {"D", "N"}:
            raise ValueError("daynight must be D or N")
        return v

    @field_validator("acquired_at")
    @classmethod
    def _not_future(cls, v: datetime):
        if v > datetime.now(timezone.utc) + timedelta(hours=6):
            raise ValueError("acquisition time is in the future")
        return v


@dataclass
class ParseResult:
    observations: list[FirmsObservation] = field(default_factory=list)
    total_rows: int = 0
    rejected: int = 0
    out_of_region: int = 0
    duplicates_in_batch: int = 0
    errors: list[str] = field(default_factory=list)


def _num(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _str(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    return s or None


def _confidence(instrument: str, raw: str | None) -> tuple[str | None, int | None]:
    if raw is None:
        return None, None
    if instrument == "MODIS":
        try:
            pct = int(round(float(raw)))
        except ValueError:
            return None, None
        pct = max(0, min(100, pct))
        # FIRMS MODIS guidance: <30 low, 30-79 nominal, >=80 high.
        level = "low" if pct < 30 else ("nominal" if pct < 80 else "high")
        return level, pct
    return VIIRS_CONFIDENCE.get(raw.lower()), None


def make_record_key(product: str, acq_date: str, acq_time: str, lat: float, lon: float) -> str:
    return f"{product}|{acq_date}|{acq_time}|{lat:.5f}|{lon:.5f}"


class _Region(Protocol):
    def contains(self, lat: float, lon: float) -> bool: ...


def parse_firms_csv(csv_text: str, product: str, region: _Region | None = None) -> ParseResult:
    """Parse one FIRMS CSV. Rows outside `region` (the India monitoring area) are counted
    in `out_of_region` and discarded."""
    spec = PRODUCTS[product]
    result = ParseResult()
    try:
        frame = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    except Exception as exc:  # malformed CSV
        result.errors.append(f"CSV parse failure: {exc}")
        return result

    frame.columns = [c.strip().lower() for c in frame.columns]
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    missing = required - set(frame.columns)
    if missing:
        result.errors.append(f"missing required columns: {sorted(missing)}")
        return result

    bright_col = "bright_ti4" if "bright_ti4" in frame.columns else "brightness"
    bright2_col = "bright_ti5" if "bright_ti5" in frame.columns else "bright_t31"
    seen: set[str] = set()

    for row in frame.to_dict("records"):
        result.total_rows += 1
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            if region is not None and not region.contains(lat, lon):
                result.out_of_region += 1
                continue
            acq_date = str(row["acq_date"]).strip()
            acq_time = str(row["acq_time"]).strip().zfill(4)
            acquired_at = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            instrument = (_str(row.get("instrument")) or spec.instrument).upper()
            satellite = _str(row.get("satellite"))
            conf_raw = _str(row.get("confidence"))
            conf_level, conf_pct = _confidence(instrument, conf_raw)
            key = make_record_key(product, acq_date, acq_time, lat, lon)
            if key in seen:
                result.duplicates_in_batch += 1
                continue
            obs = FirmsObservation(
                source_record_key=key,
                product=product,
                instrument=instrument,
                satellite=satellite,
                satellite_name=SATELLITE_NAMES.get((satellite or "").upper(), satellite),
                latitude=lat,
                longitude=lon,
                brightness=_num(row.get(bright_col)),
                brightness_2=_num(row.get(bright2_col)),
                frp=_num(row.get("frp")),
                scan=_num(row.get("scan")),
                track=_num(row.get("track")),
                acq_date=acq_date,
                acq_time=acq_time,
                acquired_at=acquired_at,
                confidence_raw=conf_raw,
                confidence_level=conf_level,
                confidence_pct=conf_pct,
                daynight=_str(row.get("daynight")),
                version=_str(row.get("version")),
            )
            seen.add(key)
            result.observations.append(obs)
        except (ValueError, KeyError, ValidationError) as exc:
            result.rejected += 1
            if len(result.errors) < 20:
                result.errors.append(f"row {result.total_rows}: {str(exc).splitlines()[0][:200]}")
    return result
