"""Build ThermoSentinel's India monitoring area from official-claim and maritime sources.

Output: database/boundaries/india_monitoring_area.geojson with two features
  role=land             India's boundary as claimed by the Government of India
                        (Natural Earth 1:10m "Admin 0 - Countries, point of view: India", public domain).
  role=monitoring_area  land UNION India's Exclusive Economic Zone (Marine Regions EEZ v12, CC BY 4.0:
                        mainland EEZ MRGID 8480 + Andaman & Nicobar EEZ MRGID 8333), so offshore
                        platforms and flares (e.g. Mumbai High) are monitored.

The output is committed to the repository so the API never depends on these downloads at
runtime. Re-run to refresh:  python data_pipeline/build_india_boundary.py
Requires the backend venv plus `pyshp` (backend/requirements-dev.txt).
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
import httpx
import shapefile  # pyshp
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries_ind.zip"
EEZ_URL = (
    "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=MarineRegions:eez&cql_filter=sovereign1=%27India%27&outputFormat=application/json"
)
EEZ_MRGIDS = {8480, 8333}
OUT = _bootstrap.REPO_ROOT / "database" / "boundaries" / "india_monitoring_area.geojson"

# Morphological closing radius (degrees, ~1 km) fills slivers where the 1:10m land outline and
# the higher-resolution EEZ baseline do not meet exactly, so coastal sites are not excluded.
CLOSING_DEG = 0.01
EEZ_SIMPLIFY_DEG = 0.003  # ~300 m; open-sea outline only

# Sanity checks: (label, lon, lat, expected inside land, expected inside monitoring area)
CHECKS = [
    ("New Delhi", 77.209, 28.614, True, True),
    ("Jamnagar refinery", 69.866, 22.337, True, True),
    ("Leh, Ladakh", 77.577, 34.152, True, True),
    ("Aksai Chin (claimed)", 79.5, 35.2, True, True),
    ("Gilgit (claimed)", 74.31, 35.92, True, True),
    ("Tawang, Arunachal Pradesh", 91.86, 27.59, True, True),
    ("Port Blair", 92.73, 11.62, True, True),
    ("Mumbai High offshore field", 71.3, 19.4, False, True),
    ("Lahore, Pakistan", 74.35, 31.55, False, False),
    ("Kathmandu, Nepal", 85.32, 27.71, False, False),
    ("Dhaka, Bangladesh", 90.41, 23.81, False, False),
    ("Colombo, Sri Lanka", 79.86, 6.93, False, False),
]


def fetch(url: str) -> bytes:
    with httpx.Client(timeout=180, headers={"User-Agent": "ThermoSentinel boundary builder"}, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def load_india_land():
    archive = zipfile.ZipFile(io.BytesIO(fetch(NE_URL)))
    base = next(n[:-4] for n in archive.namelist() if n.endswith(".shp"))
    version = next((archive.read(n).decode().strip() for n in archive.namelist() if n.endswith("VERSION.txt")), "unknown")
    reader = shapefile.Reader(
        shp=io.BytesIO(archive.read(base + ".shp")),
        dbf=io.BytesIO(archive.read(base + ".dbf")),
        shx=io.BytesIO(archive.read(base + ".shx")),
    )
    fields = [f[0] for f in reader.fields[1:]]
    for sr in reader.iterShapeRecords():
        record = dict(zip(fields, sr.record))
        if record.get("ADM0_A3") == "IND":
            return shape(sr.shape.__geo_interface__), version
    raise RuntimeError("India (ADM0_A3=IND) not found in Natural Earth India point-of-view file")


def load_eez():
    payload = json.loads(fetch(EEZ_URL))
    parts, names = [], []
    for feature in payload["features"]:
        props = feature["properties"]
        if int(props["mrgid"]) in EEZ_MRGIDS:
            parts.append(shape(feature["geometry"]))
            names.append(f"{props['geoname']} (MRGID {props['mrgid']})")
    if len(parts) != len(EEZ_MRGIDS):
        raise RuntimeError(f"Expected {len(EEZ_MRGIDS)} Indian EEZ features, got {len(parts)}")
    return unary_union(parts), names


def main() -> int:
    print("Downloading Natural Earth (India point of view)...")
    land, ne_version = load_india_land()
    print("Downloading Marine Regions EEZ (India)...")
    eez, eez_names = load_eez()

    eez = eez.simplify(EEZ_SIMPLIFY_DEG, preserve_topology=True)
    area = unary_union([land, eez]).buffer(CLOSING_DEG).buffer(-CLOSING_DEG)
    area = unary_union([area, land])  # never lose any claimed land to the erosion step

    failures = []
    for label, lon, lat, in_land, in_area in CHECKS:
        p = Point(lon, lat)
        got_land, got_area = land.covers(p), area.covers(p)
        ok = got_land == in_land and got_area == in_area
        print(f"  {'ok ' if ok else 'FAIL'} {label:32s} land={got_land!s:5s} monitoring={got_area}")
        if not ok:
            failures.append(label)
    if failures:
        print(f"Sanity checks failed: {failures}", file=sys.stderr)
        return 1

    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    feature_collection = {
        "type": "FeatureCollection",
        "name": "india_monitoring_area",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "role": "land",
                    "name": "India",
                    "source": "Natural Earth 1:10m Admin 0 - Countries, point of view: India",
                    "source_version": ne_version,
                    "source_url": NE_URL,
                    "license": "Public domain (Natural Earth)",
                    "retrieved_at": retrieved,
                },
                "geometry": mapping(land),
            },
            {
                "type": "Feature",
                "properties": {
                    "role": "monitoring_area",
                    "name": "India (land + Exclusive Economic Zone)",
                    "source": "Natural Earth India POV land boundary UNION Marine Regions EEZ: " + "; ".join(eez_names),
                    "source_url": EEZ_URL,
                    "license": "Land: public domain (Natural Earth). EEZ: CC BY 4.0 - Flanders Marine Institute (2023), Maritime Boundaries Geodatabase v12, marineregions.org",
                    "processing": f"EEZ simplified {EEZ_SIMPLIFY_DEG} deg; union closed with {CLOSING_DEG} deg buffer to remove coastline slivers",
                    "retrieved_at": retrieved,
                },
                "geometry": mapping(area),
            },
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(feature_collection, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB); bounds {[round(v, 3) for v in area.bounds]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
