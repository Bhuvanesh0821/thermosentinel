"""Overpass API access for thermally relevant industrial infrastructure in OpenStreetMap."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.errors import UpstreamError
from app.geo.region import BBox
from app.ingestion.http import request_with_retries

log = logging.getLogger(__name__)

# OSM selectors for facilities that can plausibly produce satellite-observable heat.
# Only exact key=value (indexed, cheap) filters are sent to the shared public Overpass
# servers; finer filtering (e.g. excluding solar/wind/hydro plants) happens locally in
# classify.is_thermally_relevant().
INDUSTRIAL_VALUES = [
    "refinery", "oil", "gas", "petroleum_terminal", "chemical", "petrochemical", "fertilizer", "fertiliser",
    "steelmaker", "steel", "steel_mill", "iron", "ironworks", "metallurgy", "smelter", "smelting",
    "aluminium_smelting", "foundry", "coking", "coke", "coking_plant", "cement", "brickyard", "mine", "coal",
    "lng", "gas_processing", "glass",
]
PLANT_SOURCES = ["coal", "gas", "oil", "diesel", "biomass", "biofuel", "waste", "lignite", "biogas"]
SELECTORS = (
    [f'nwr["power"="plant"]["plant:source"="{src}"]' for src in PLANT_SOURCES]
    + ['nwr["power"="plant"]["plant:method"="combustion"]']
    + [f'nwr["industrial"="{value}"]' for value in INDUSTRIAL_VALUES]
    + [
        'nwr["man_made"="works"]["product"]',
        'nwr["man_made"="flare"]',
        'nwr["man_made"="offshore_platform"]',  # e.g. Mumbai High (inside India's EEZ)
        'nwr["man_made"="kiln"]',
        'nwr["landuse"="quarry"]["resource"]',
        # Major sites often mapped only as a named industrial area (e.g. "Bokaro Thermal Power Station").
        'nwr["landuse"="industrial"]["name"~"steel|ispat|refinery|thermal power|super thermal|smelter|alumin|'
        'cement|fertili|petrochem|coke oven|sponge iron|LNG",i]',
    ]
)


@dataclass
class OverpassResult:
    elements: list[dict]
    osm_base_timestamp: str | None
    endpoint: str


class OverpassError(UpstreamError):
    code = "overpass_error"


MAXSIZE_BYTES = 128 * 1024 * 1024  # a modest declared budget is admitted far more readily when servers are busy


def build_query(tile: BBox, timeout_s: int) -> str:
    body = "\n  ".join(f"{sel};" for sel in SELECTORS)
    # Nodes carry lat/lon; ways get full geometry (for footprints); relations get a centre point.
    return (
        f"[out:json][timeout:{timeout_s}][maxsize:{MAXSIZE_BYTES}][bbox:{tile.as_overpass()}];\n"
        f"(\n  {body}\n)->.all;\n"
        "node.all;out body;\n"
        "way.all;out body geom;\n"
        "rel.all;out body center;\n"
    )


class OverpassClient:
    def __init__(self, urls: list[str], http: httpx.Client, timeout_s: int):
        if not urls:
            raise ValueError("at least one Overpass endpoint is required")
        self.urls = urls
        self.http = http
        self.timeout_s = timeout_s

    def fetch(self, tile: BBox) -> OverpassResult:
        query = build_query(tile, self.timeout_s)
        errors: list[str] = []
        for url in self.urls:  # fail over across public Overpass instances
            try:
                response = request_with_retries(
                    self.http, "POST", url, data={"data": query}, attempts=2, backoff_s=5.0,
                    timeout=self.timeout_s + 30,
                )
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {exc.__class__.__name__}")
                continue
            if response.status_code != 200:
                errors.append(f"{url}: HTTP {response.status_code}")
                continue
            try:
                payload = response.json()
            except ValueError:
                errors.append(f"{url}: non-JSON response")
                continue
            remark = payload.get("remark") or ""
            if "error" in remark.lower():
                # Overpass reports timeouts / memory exhaustion in `remark` with HTTP 200.
                errors.append(f"{url}: {remark[:160]}")
                continue
            return OverpassResult(
                elements=payload.get("elements", []),
                osm_base_timestamp=(payload.get("osm3s") or {}).get("timestamp_osm_base"),
                endpoint=url,
            )
        raise OverpassError(f"All Overpass endpoints failed for tile {tile.as_overpass()}: {' | '.join(errors)}")
