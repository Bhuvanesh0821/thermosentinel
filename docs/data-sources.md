# Data sources

Every map point, metric and assessment is derived from the sources below. Nothing is
synthesised. When a source is unavailable the UI shows an explicit unavailable/empty state.

| Source | Used for | Access | Licence |
|--------|----------|--------|---------|
| **NASA FIRMS** - VIIRS S-NPP, NOAA-20, NOAA-21 (375 m) and MODIS Terra/Aqua (1 km) NRT active fire | Thermal detections | Area API with `NASA_FIRMS_MAP_KEY` (region extent, up to 5 days/request, backfill) **or** keyless public NRT CSV (South Asia, 24h/48h/7d) | NASA open data; attribution requested |
| **OpenStreetMap** via Overpass API | Industrial facilities (points + outlines) | Public Overpass endpoints with failover; 6° tiles; exact-tag queries | ODbL 1.0 - © OpenStreetMap contributors |
| **ESA WorldCover 10 m v200 (2021)** | Land-cover context around clusters | Cloud-Optimised GeoTIFFs on AWS Open Data (`esa-worldcover`), windowed range reads | CC BY 4.0 - © ESA WorldCover project 2021 / Copernicus Sentinel data |
| **Natural Earth 1:10m Admin-0, point of view: India** | India's official-claim boundary | Downloaded once by `data_pipeline/build_india_boundary.py`, committed as GeoJSON | Public domain |
| **Marine Regions Maritime Boundaries v12** (MRGID 8480, 8333) | India's EEZ (mainland + Andaman & Nicobar) | WFS download in the same build script | CC BY 4.0 - Flanders Marine Institute |
| **OpenFreeMap** (Positron style) | Light vector basemap | Keyless tiles; its own boundary layers are hidden | © OpenMapTiles, data © OpenStreetMap contributors |
| **EOX Sentinel-2 cloudless 2021** | Satellite basemap | Keyless WMTS tiles | CC BY-NC-SA 4.0 - EOX IT Services GmbH |
| **NASA GIBS** VIIRS S-NPP true colour | Daily imagery basemap | Keyless WMTS tiles | NASA open data |
| **Neon PostgreSQL + PostGIS** | Primary datastore | `DATABASE_URL` (TLS) | - |

## India-only coverage

Coverage is restricted to India's officially claimed territory (all of Jammu & Kashmir,
Ladakh including Aksai Chin, and Arunachal Pradesh) plus its EEZ, so offshore platforms such as
Mumbai High are monitored. Every FIRMS detection and OSM facility is tested against this
polygon **before storage**; anything outside is counted and discarded. The boundary builder
verifies 12 reference points (e.g. Gilgit, Aksai Chin and Mumbai High inside; Lahore,
Kathmandu, Dhaka and Colombo outside) and refuses to write the file if any check fails.

Accuracy: the Natural Earth boundary is 1:10m scale (roughly 1 km positional accuracy), so a
detection within about a kilometre of an international land border may be assigned to the
wrong side. The map masks everything outside the monitoring area and draws only the official
boundary; the basemap's own border lines are hidden.

## Provenance kept in the database

* `thermal_observations`: `source_id`, `source_mode` (api/public_feed), `product`, raw
  confidence, `ingestion_run_id`, `ingested_at`, deterministic `source_record_key` (dedupe).
* `industrial_facilities`: OSM element (`source_ref`, e.g. `way/91585872`), raw `tags`,
  OSM snapshot time (`source_timestamp`), `ingestion_run_id`.
* `land_cover`: dataset version, tile, sample radius and effective resolution.
* `ingestion_runs`: every fetch with parameters (API key masked), counts and errors.
* `data_sources`: live status, last success, last error, record counts.
