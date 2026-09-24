# Stage 1 report - foundation and real-data pipeline

Date: 2026-09-24. Scope: the Stage 1 brief (architecture, database, real-data ingestion, GIS APIs,
clustering, proximity, persistence, intelligence, professional UI). Nothing is deployed.

## Verification results

All results below come from real data: NASA FIRMS (public NRT feed, 16-23 Sep 2026),
OpenStreetMap (snapshot 2026-09-22) and ESA WorldCover. Development testing first ran against
a disposable PostgreSQL 17.11 + PostGIS 3.6.2 server; the final verification ran on the
project's **Neon database (PostgreSQL 18.6 + PostGIS 3.6.4, AWS ap-southeast-1, pooled
endpoint, TLS with channel binding)** with identical results.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Backend starts | ✅ | Starts with and without a database; `/api/health` reports DB, scheduler and pipeline state |
| 2 | Frontend starts | ✅ | Vite dev server and production build (`vite preview`); map ready in ~6 s in production |
| 3 | **Neon** connection works | ✅ | Migrations 0001-0004 applied on Neon (PostGIS enabled); the API's scheduler ran the full pipeline on Neon unattended in 19 min (FIRMS → 30/30 facility tiles → analysis); all 25 endpoints return the stored data |
| 4 | NASA FIRMS real API works | ✅ (keyless public feed) | 14,402 rows fetched → **5,140 inside India**, 9,262 outside discarded, 0 rejected. Keyed Area API is implemented; activates when `NASA_FIRMS_MAP_KEY` is set |
| 5 | Real thermal observations reach the backend | ✅ | `/api/firms` total 5,140 with product, satellite, confidence, source mode and ingestion run on every row |
| 6 | Real industrial facility data reaches the backend | ✅ | 30/30 Overpass tiles, **6,912 facilities in India** (3,333 outside discarded), incremental + resumable |
| 7 | Database stores observations | ✅ | Re-ingestion inserts 0 (dedupe key); PostGIS confirms **0 stored records outside India** |
| 8 | Clustering operates on real observations | ✅ | 5,140 detections → 1,033 ST-DBSCAN clusters (415 multi-detection); ids stable across runs (integration test) |
| 9 | GIS map displays backend data | ✅ | Detections, clusters, incidents, risk zones, facilities + outlines, land cover, India mask/boundary - screenshot-checked |
| 10 | No fake thermal data | ✅ | Every value traces to FIRMS/OSM/WorldCover rows; test fixtures are unmodified real FIRMS rows (documented) |
| 11 | API documentation works | ✅ | `/api/docs` (Swagger), `/api/redoc`, `/api/openapi.json`; 25 endpoints checked with real data |
| 12 | Error / empty states work | ✅ | No-DB: 503 `database_not_configured` envelopes + guided UI states (tested); empty windows, unavailable basemap, "no data held" chart buckets |

## What the real data produced

* Analysis in **16 s**: 1,033 clusters; 214 within 3 km of a mapped facility; persistence
  (8 days of coverage): 96 persistent, 207 recurring, 730 transient; 297 WorldCover samples.
* Top-ranked events are persistent heat **inside the mapped footprints** of Tata Steel
  (Jamshedpur, Meramandali), Bokaro, JSW, Jindal Angul, Bhushan, Nagarnar and Visakhapatnam steel
  plants and Reliance's Jamnagar refinery - labelled "potential industrial thermal event", never
  "confirmed".
* 183 incidents opened (124 still active/monitoring), 124 alerts with in-app notifications; voice
  briefing generated from the same data.

## Tests

* `pytest`: 75 unit tests pass (parser, India clipping, clustering, persistence, intelligence,
  facility classification, API error states). They caught a pandas-3 timestamp-unit bug that would
  have chained unrelated days into one cluster.
* `tests/test_db_integration.py` (3 tests, PostGIS): migrations, idempotent India-only ingest,
  full analysis with stable cluster ids - pass against the local PostgreSQL 17 + PostGIS 3.6.
* Chart palettes validated with the dataviz CVD checks (facility colours were replaced after the
  old set failed).

## Neon results

| Item | Value |
|------|-------|
| Detections stored | 5,140 (all inside India) |
| Facilities | 6,913 active, 30/30 tiles |
| Clusters | 1,033 |
| Open incidents / alerts | 116 / 116 (8 critical, 39 high, 69 medium) |
| Network round trip, development PC → Neon Singapore | ~210 ms per query (measured with `SELECT 1`; TCP connect alone 214 ms) |

API responses from the development PC take 1-3 s because each request makes several database
round trips at ~210 ms. Deploying the API in the same region as Neon (Stage 2) removes this.

## Known limitations (honest)

* Latency from a remote PC to Neon (see above) until the API is co-located with the database.
* Keyless FIRMS feed gives 7 days of history; persistence strengthens as history accumulates (or
  immediately with a MAP_KEY backfill).
* WorldCover sampling is capped at 300 clusters per run; the rest fill in on later runs.
* Natural Earth boundary is 1:10m (~1 km near international borders).
* Docker files are written but not built (Docker is not installed on the development machine).
* Authentication/roles are not part of Stage 1 (profile shows "Local session").
