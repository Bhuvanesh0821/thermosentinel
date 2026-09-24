# database/

* `migrations/` - forward-only SQL migrations applied in order by `backend/app/db/migrate.py`
  (automatically on API start-up when `AUTO_MIGRATE=true`, or via
  `python data_pipeline/pipeline.py migrate`). Applied versions and checksums are tracked in
  `schema_migrations`; an applied file that is later edited is reported, never re-run.
  * `0001_extensions.sql` - PostGIS + `set_updated_at()` trigger function.
  * `0002_core_schema.sql` - data_sources, ingestion_runs, industrial_facilities, land_cover,
    thermal_clusters, thermal_observations, cluster_facility_proximity, incidents, alerts,
    notifications, system_events, job_locks.
  * `0003_monitoring_regions.sql` - India monitoring area (official boundary + EEZ).
  * `0004_facility_tiles.sql` - per-tile progress of the OSM facility refresh (resumable loads).
* `boundaries/india_monitoring_area.geojson` - built by
  `data_pipeline/build_india_boundary.py` (Natural Earth India point-of-view + Marine Regions
  EEZ, with 12 automated sanity checks). Loaded into `monitoring_regions` at start-up.

Spatial design: every point is stored as exact `latitude`/`longitude` plus a
`geography(Point, 4326)` column with a GIST index, so metre-based `ST_DWithin` / `ST_Distance`
and KNN searches (nearest facility, detections within 1 km) are index-assisted. Facility
outlines are `geography(Geometry, 4326)` so a detection can be tested for being *inside* a site.
