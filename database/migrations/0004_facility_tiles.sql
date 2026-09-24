-- 0004: Per-tile progress for the OpenStreetMap facility refresh.
-- Each Overpass tile is saved as soon as it completes; later runs only retry tiles that
-- failed or are older than FACILITIES_REFRESH_HOURS.
CREATE TABLE facility_tiles (
    tile_key          text PRIMARY KEY,          -- 'south,west,north,east'
    west              double precision NOT NULL,
    south             double precision NOT NULL,
    east              double precision NOT NULL,
    north             double precision NOT NULL,
    status            text NOT NULL CHECK (status IN ('success', 'failed')),
    element_count     integer NOT NULL DEFAULT 0,
    facility_count    integer NOT NULL DEFAULT 0,
    endpoint          text,
    osm_base_timestamp timestamptz,
    last_attempt_at   timestamptz NOT NULL DEFAULT now(),
    last_success_at   timestamptz,
    last_error        text,
    ingestion_run_id  bigint REFERENCES ingestion_runs(id) ON DELETE SET NULL
);
